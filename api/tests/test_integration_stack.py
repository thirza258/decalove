"""The whole stack: API on real MongoDB and real MinIO.

Everything else in the suite runs on the offline seams. This is the only place
the production configuration is actually exercised -- including the legacy
scene/image CRUD, which is MongoDB-only and returns 503 without it.

Skips itself when the stack is not running.
"""

from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from minio import Minio
from motor.motor_asyncio import AsyncIOMotorClient

from conftest import needs_minio, needs_mongo
from app.assets.png import gradient_png
from app.config import settings

pytestmark = [needs_mongo, needs_minio, pytest.mark.integration]


@pytest.fixture
def stack(monkeypatch):
    """A TestClient wired to a throwaway database and bucket."""
    suffix = uuid.uuid4().hex[:10]
    database = f"decalove_test_{suffix}"
    bucket = f"decalove-test-{suffix}"

    monkeypatch.setattr(settings, "STORAGE_BACKEND", "mongo")
    monkeypatch.setattr(settings, "ASSET_BACKEND", "minio")
    monkeypatch.setattr(settings, "MONGODB_DB_NAME", database)
    monkeypatch.setattr(settings, "MINIO_BUCKET_NAME", bucket)
    monkeypatch.setattr(settings, "OPENROUTER_API_KEY", "")
    monkeypatch.setattr(settings, "IMAGE_GENERATION_ENABLED", True)

    from app.storage import storage

    monkeypatch.setattr(storage, "client", None)

    from app.main import app

    try:
        yield app, database
    finally:
        client = AsyncIOMotorClient(settings.MONGODB_URL, serverSelectionTimeoutMS=3000)
        client.delegate.drop_database(database)
        client.close()

        minio = Minio(
            settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=settings.MINIO_SECURE,
        )
        if minio.bucket_exists(bucket):
            for obj in minio.list_objects(bucket, recursive=True):
                minio.remove_object(bucket, obj.object_name)
            minio.remove_bucket(bucket)


def drain(client, game_id, budget=30):
    shown = []
    for _ in range(budget):
        body = client.get(f"/api/v1/games/{game_id}/steps/next", params={"wait_ms": 3000}).json()
        if body["status"] == "ready":
            shown.append(body["step"])
        elif body["status"] == "awaiting_player":
            return shown, body["step"]
        elif body["status"] == "ended":
            return shown, None
    raise AssertionError("never reached a decision point")


class TestStackWiring:
    def test_health_reports_the_real_backends(self, stack):
        app, _ = stack
        with TestClient(app) as client:
            body = client.get("/health").json()
            assert body["storage"] == "mongo"
            assert body["assets"] == "minio"
            assert body["mongodb"] is True


class TestPersistence:
    def test_a_game_survives_a_process_restart(self, stack):
        """The point of MongoDB. In-memory storage would lose this."""
        app, _ = stack

        with TestClient(app) as client:
            game_id = client.post("/api/v1/games", json={"player_name": "Rin"}).json()["game_id"]
            shown, decision = drain(client, game_id)
            client.post(
                f"/api/v1/games/{game_id}/choices",
                json={"step_id": decision["step_id"], "choice_id": decision["next_choices"][0]["id"]},
            )
            drain(client, game_id)
            before = client.get(f"/api/v1/games/{game_id}").json()

        # A completely new runtime, same database.
        with TestClient(app) as client:
            after = client.get(f"/api/v1/games/{game_id}").json()

            assert after["player"]["name"] == "Rin"
            assert after["current_step_index"] == before["current_step_index"]
            assert after["characters"] == before["characters"]
            assert after["world"] == before["world"]
            assert game_id in client.get("/api/v1/games").json()

    def test_the_story_continues_after_a_restart(self, stack):
        app, _ = stack
        with TestClient(app) as client:
            game_id = client.post("/api/v1/games", json={"player_name": "Rin"}).json()["game_id"]
            _, decision = drain(client, game_id)

        with TestClient(app) as client:
            response = client.post(
                f"/api/v1/games/{game_id}/choices",
                json={"step_id": decision["step_id"], "choice_id": decision["next_choices"][0]["id"]},
            )
            assert response.status_code == 202
            shown, following = drain(client, game_id)
            assert shown, "the story did not resume"
            assert following is not None

    def test_character_memories_are_persisted(self, stack):
        app, database = stack
        with TestClient(app) as client:
            game_id = client.post("/api/v1/games", json={"player_name": "Rin"}).json()["game_id"]
            drain(client, game_id)
            client.post(
                f"/api/v1/games/{game_id}/actions",
                json={"input": "I tell Aiko exactly how I feel about her."},
            )
            drain(client, game_id)

        mongo = AsyncIOMotorClient(settings.MONGODB_URL, serverSelectionTimeoutMS=3000)
        try:
            memories = list(mongo.delegate[database]["character_memories"].find({"game_id": game_id}))
            assert memories, "a significant beat should have written a memory"
            assert memories[0]["embedding"], "memories need embeddings to be retrievable"
        finally:
            mongo.close()


class TestArtOnMinio:
    def test_generated_art_is_stored_in_minio_and_served(self, stack):
        app, _ = stack
        with TestClient(app) as client:
            game_id = client.post("/api/v1/games", json={"player_name": "Rin"}).json()["game_id"]

            reference = None
            for _ in range(3):
                shown, decision = drain(client, game_id)
                ready = [
                    s["background_asset"]
                    for s in shown
                    if s["background_asset"] and s["background_asset"]["status"] == "ready"
                ]
                if ready:
                    reference = ready[0]
                    break
                if decision is None:
                    break
                client.post(
                    f"/api/v1/games/{game_id}/choices",
                    json={
                        "step_id": decision["step_id"],
                        "choice_id": decision["next_choices"][0]["id"],
                    },
                )

            assert reference is not None, "no art reached a delivered step"
            assert reference["url"].startswith("http"), "MinIO should serve a presigned URL directly"

            metadata = client.get(f"/api/v1/assets/{reference['asset_id']}").json()
            assert metadata["object_key"].startswith("backgrounds/")

            proxied = client.get(f"/api/v1/assets/{reference['asset_id']}/view")
            assert proxied.status_code == 200
            assert proxied.content[:8] == b"\x89PNG\r\n\x1a\n"


class TestLegacyCrud:
    """The scene/image endpoints that predate the story engine."""

    def test_seed_and_scene_lifecycle(self, stack):
        app, _ = stack
        with TestClient(app) as client:
            seeded = client.post("/api/v1/seed")
            assert seeded.status_code == 200
            assert seeded.json()["scene"]["title"] == "First Encounter"

            created = client.post(
                "/api/v1/scenes",
                json={
                    "title": "Rooftop",
                    "dialogue": [{"character": "Aiko", "text": "You came.", "emotion": "surprised"}],
                    "background_image_url": "backgrounds/rooftop.png",
                    "choices": [{"text": "I promised.", "next_scene_id": "000000000000000000000001"}],
                },
            )
            assert created.status_code == 201
            scene_id = created.json()["_id"]

            assert client.get(f"/api/v1/scenes/{scene_id}").json()["title"] == "Rooftop"
            assert len(client.get("/api/v1/scenes").json()) == 2

            updated = client.put(f"/api/v1/scenes/{scene_id}", json={"title": "Rooftop, later"})
            assert updated.json()["title"] == "Rooftop, later"
            assert updated.json()["dialogue"], "a partial update must not wipe untouched fields"

            assert client.delete(f"/api/v1/scenes/{scene_id}").status_code == 204
            assert client.get(f"/api/v1/scenes/{scene_id}").status_code == 404

    def test_malformed_scene_ids_are_rejected_with_400(self, stack):
        app, _ = stack
        with TestClient(app) as client:
            assert client.get("/api/v1/scenes/not-an-objectid").status_code == 400
            assert client.delete("/api/v1/scenes/not-an-objectid").status_code == 400
            assert client.put("/api/v1/scenes/not-an-objectid", json={"title": "x"}).status_code == 400

    def test_image_upload_view_and_scene_resolution(self, stack):
        app, _ = stack
        payload = gradient_png(24, 16, "#ff9e7d", "#2b3a67", seed="legacy")

        with TestClient(app) as client:
            uploaded = client.post(
                "/api/v1/images/upload",
                files={"file": ("rooftop.png", payload, "image/png")},
                data={"image_type": "background"},
            )
            assert uploaded.status_code == 201
            image = uploaded.json()
            assert image["object_key"].startswith("backgrounds/")
            assert image["size_bytes"] == len(payload)

            assert client.get(f"/api/v1/images/{image['_id']}").json()["url"].startswith("http")

            viewed = client.get(f"/api/v1/images/{image['_id']}/view")
            assert viewed.status_code == 200
            assert viewed.content == payload

            scene_id = client.post(
                "/api/v1/scenes",
                json={"title": "S", "background_image_url": image["object_key"]},
            ).json()["_id"]

            full = client.get(f"/api/v1/scenes/{scene_id}/full").json()
            assert full["background_image_full_url"].startswith("http")

    def test_missing_images_are_404_not_500(self, stack):
        app, _ = stack
        with TestClient(app) as client:
            assert client.get("/api/v1/images/000000000000000000000001").status_code == 404
            assert client.get("/api/v1/images/nonsense").status_code == 400
