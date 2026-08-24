"""Error paths and edges: the branches only a bad request or a broken service reaches."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from app.content import get_world
from app.content.registry import default_world
from app.domain.story import GeneratedStep
from app.domain.validation import ValidationReport, Violation
from app.models.scene import validate_object_id


class TestWorldRegistry:
    def test_no_id_gives_the_default_world(self):
        assert get_world(None).id == default_world().id
        assert get_world("").id == default_world().id

    def test_a_known_id_is_returned(self):
        assert get_world("highschool_romance").id == "highschool_romance"

    def test_an_unknown_id_names_itself_in_the_error(self):
        with pytest.raises(KeyError, match="cyberpunk"):
            get_world("cyberpunk")


class TestObjectIdValidation:
    def test_a_bson_object_id_is_stringified(self):
        from bson import ObjectId

        oid = ObjectId()
        assert validate_object_id(oid) == str(oid)

    def test_a_valid_hex_string_passes_through(self):
        assert validate_object_id("000000000000000000000001") == "000000000000000000000001"

    @pytest.mark.parametrize("value", ["nonsense", "", 12345, None])
    def test_anything_else_is_rejected(self, value):
        with pytest.raises(ValueError, match="Invalid ObjectId"):
            validate_object_id(value)


class TestValidationReport:
    def test_an_empty_report_is_not_ok(self):
        assert ValidationReport().ok is False

    def test_rejected_is_distinct_from_merely_repaired(self):
        repaired = ValidationReport(
            steps=[GeneratedStep(type="narration", location="classroom", narration=".")],
            violations=[Violation(rule="state_consistency", detail="clamped", remedy="clamped")],
        )
        assert repaired.ok is True and repaired.rejected is False

        rejected = ValidationReport(
            violations=[Violation(rule="content_safety", detail="nope", remedy="rejected")]
        )
        assert rejected.rejected is True and rejected.ok is False

    def test_the_summary_is_readable(self):
        clean = ValidationReport(
            steps=[GeneratedStep(type="narration", location="classroom", narration=".")]
        )
        assert clean.summary() == "1 steps, clean"

        noisy = ValidationReport(
            steps=[GeneratedStep(type="narration", location="classroom", narration=".")],
            violations=[
                Violation(rule="player_agency", detail=f"issue {i}", remedy="rewritten", step_index=i)
                for i in range(8)
            ],
        )
        summary = noisy.summary()
        assert "8 violation(s)" in summary
        assert summary.count(";") <= 4, "the summary should not print every violation"
        assert "[player_agency] step 0" in summary


class TestMongoGuard:
    def test_the_legacy_routes_say_how_to_fix_a_missing_mongo(self, client):
        """The game engine runs without MongoDB; the older CRUD does not."""
        for path in ("/api/v1/scenes", "/api/v1/images/000000000000000000000001"):
            response = client.get(path)
            assert response.status_code == 503
            assert "docker compose up -d" in response.json()["detail"]

        assert client.post("/api/v1/seed").status_code == 503

    def test_the_dependency_passes_when_mongo_is_up(self, monkeypatch):
        from app import dependencies

        monkeypatch.setattr(dependencies, "mongo_available", lambda: True)
        assert dependencies.require_mongo() is None

        monkeypatch.setattr(dependencies, "mongo_available", lambda: False)
        with pytest.raises(HTTPException) as error:
            dependencies.require_mongo()
        assert error.value.status_code == 503


class TestGameRoutes:
    def test_save_and_delete_report_missing_games(self, client):
        assert client.get("/api/v1/games/nope/save").status_code == 404
        assert client.delete("/api/v1/games/nope").status_code == 404

    def test_acting_on_a_missing_game_is_a_404(self, client):
        assert client.post("/api/v1/games/nope/actions", json={"input": "hi"}).status_code == 404
        assert (
            client.post(
                "/api/v1/games/nope/choices", json={"step_id": "s", "choice_id": "c"}
            ).status_code
            == 404
        )

    def test_an_unknown_step_id_is_a_conflict_not_a_crash(self, client):
        game_id = client.post("/api/v1/games", json={"player_name": "Kai"}).json()["game_id"]
        response = client.post(
            f"/api/v1/games/{game_id}/choices",
            json={"step_id": "step_99999", "choice_id": "choice_1"},
        )
        assert response.status_code == 409
        assert "unknown step" in response.json()["detail"]

    def test_answering_a_non_decision_step_is_rejected(self, client):
        game_id = client.post("/api/v1/games", json={"player_name": "Kai"}).json()["game_id"]
        client.get(f"/api/v1/games/{game_id}/steps/next", params={"wait_ms": 2000})

        response = client.post(
            f"/api/v1/games/{game_id}/choices",
            json={"step_id": "step_00000", "choice_id": "choice_1"},
        )
        assert response.status_code == 409
        assert "not a decision point" in response.json()["detail"]

    def test_acting_on_an_ended_game_is_a_conflict(self, client):
        import asyncio

        game_id = client.post("/api/v1/games", json={"player_name": "Kai"}).json()["game_id"]
        repository = client.app.state.runtime.games

        async def end():
            session = await repository.get(game_id)
            session.ended = True
            await repository.save(session)

        asyncio.run(end())

        assert client.post(f"/api/v1/games/{game_id}/actions", json={"input": "hi"}).status_code == 409
        assert client.get(f"/api/v1/games/{game_id}/steps/next").json()["status"] == "ended"

    def test_input_longer_than_the_limit_is_rejected(self, client):
        game_id = client.post("/api/v1/games", json={"player_name": "Kai"}).json()["game_id"]
        response = client.post(f"/api/v1/games/{game_id}/actions", json={"input": "x" * 601})
        assert response.status_code == 422

    def test_the_long_poll_window_is_capped(self, client):
        game_id = client.post("/api/v1/games", json={"player_name": "Kai"}).json()["game_id"]
        assert (
            client.get(f"/api/v1/games/{game_id}/steps/next", params={"wait_ms": 999999}).status_code
            == 422
        )

    def test_listing_is_bounded(self, client):
        for _ in range(3):
            client.post("/api/v1/games", json={"player_name": "Kai"})
        assert len(client.get("/api/v1/games", params={"limit": 2}).json()) == 2
        assert client.get("/api/v1/games", params={"limit": 0}).status_code == 422


class TestAssetServiceFailures:
    async def test_a_store_that_cannot_write_degrades_to_unavailable(self, tmp_path):
        from app.agents.visual import AssetSpec
        from app.assets.base import AssetStoreError
        from app.domain.enums import AssetStatus
        from app.llm.placeholder_image import PlaceholderImageProvider
        from app.repositories.memory_repo import InMemoryAssetRepository
        from app.services.asset_service import AssetService

        class BrokenStore:
            name = "broken"

            async def put(self, key, data, content_type):
                raise AssetStoreError("disk on fire")

            async def get(self, key):
                raise AssetStoreError("disk on fire")

            async def exists(self, key):
                return False

            async def url(self, key):
                return None

        service = AssetService(
            InMemoryAssetRepository(), BrokenStore(), PlaceholderImageProvider(), enabled=True
        )
        ref = await service.ensure(AssetSpec(kind="background", cache_key="k", prompt="p"), "w")

        assert ref.status is AssetStatus.unavailable, "a broken store must not raise into the game"

    async def test_reading_an_unknown_asset_returns_none(self, tmp_path):
        from app.assets.local_store import LocalAssetStore
        from app.repositories.memory_repo import InMemoryAssetRepository
        from app.services.asset_service import AssetService

        service = AssetService(InMemoryAssetRepository(), LocalAssetStore(tmp_path), None)
        assert await service.read("nope") is None
        assert await service.metadata("nope") is None

    async def test_a_record_whose_bytes_vanished_returns_none(self, tmp_path):
        from app.assets.local_store import LocalAssetStore
        from app.domain.asset import AssetRecord
        from app.repositories.memory_repo import InMemoryAssetRepository
        from app.services.asset_service import AssetService

        repository = InMemoryAssetRepository()
        await repository.put(AssetRecord(id="a1", cache_key="k", object_key="gone.png"))
        service = AssetService(repository, LocalAssetStore(tmp_path), None)

        assert await service.read("a1") is None
        assert (await service.metadata("a1")).id == "a1"
