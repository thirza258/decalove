"""MinIO asset store, against a real server.

Skips itself when MinIO is not running.
"""

from __future__ import annotations

import uuid

import pytest
from minio import Minio

from conftest import needs_minio
from app.agents.visual import AssetSpec
from app.assets.base import AssetStoreError
from app.assets.minio_store import MinioAssetStore
from app.assets.png import gradient_png
from app.config import settings
from app.domain.enums import AssetStatus
from app.llm.placeholder_image import PlaceholderImageProvider
from app.repositories.memory_repo import InMemoryAssetRepository
from app.services.asset_service import AssetService
from app.storage import _reachable, init_minio, storage

pytestmark = [needs_minio, pytest.mark.integration]


@pytest.fixture
def bucket(monkeypatch):
    """An isolated bucket per test, removed afterwards."""
    name = f"decalove-test-{uuid.uuid4().hex[:10]}"
    monkeypatch.setattr(settings, "MINIO_BUCKET_NAME", name)
    monkeypatch.setattr(storage, "client", None)

    assert init_minio() is True
    client = Minio(
        settings.MINIO_ENDPOINT,
        access_key=settings.MINIO_ACCESS_KEY,
        secret_key=settings.MINIO_SECRET_KEY,
        secure=settings.MINIO_SECURE,
    )
    try:
        yield name
    finally:
        for obj in client.list_objects(name, recursive=True):
            client.remove_object(name, obj.object_name)
        client.remove_bucket(name)


class TestProbe:
    def test_reachability_check_is_fast_and_honest(self):
        assert _reachable(settings.MINIO_ENDPOINT) is True
        assert _reachable("127.0.0.1:59999", timeout=0.3) is False
        assert _reachable("not-a-host-at-all:9000", timeout=0.3) is False

    def test_init_creates_the_bucket_and_is_idempotent(self, bucket):
        assert init_minio() is True
        assert storage.available is True


class TestStore:
    async def test_round_trip_preserves_bytes_and_content_type(self, bucket):
        store = MinioAssetStore()
        payload = gradient_png(32, 18, "#ff9e7d", "#2b3a67", seed="rooftop")

        await store.put("backgrounds/rooftop.png", payload, "image/png")

        assert await store.exists("backgrounds/rooftop.png")
        data, content_type = await store.get("backgrounds/rooftop.png")
        assert data == payload
        assert content_type == "image/png"

    async def test_a_missing_object_reports_absent_rather_than_raising(self, bucket):
        assert await MinioAssetStore().exists("nope.png") is False

    async def test_reading_a_missing_object_raises_a_store_error(self, bucket):
        with pytest.raises(AssetStoreError, match="minio get failed"):
            await MinioAssetStore().get("nope.png")

    async def test_it_hands_back_a_presigned_url_the_client_can_fetch(self, bucket):
        import httpx

        store = MinioAssetStore()
        payload = gradient_png(8, 8, "#fff", "#000", seed="u")
        await store.put("backgrounds/u.png", payload, "image/png")

        url = await store.url("backgrounds/u.png")
        assert url and url.startswith("http")
        assert bucket in url

        # A presigned URL must work with no credentials at all -- that is the point.
        response = httpx.get(url, timeout=10)
        assert response.status_code == 200
        assert response.content == payload

    async def test_overwriting_a_key_replaces_it(self, bucket):
        store = MinioAssetStore()
        await store.put("k.png", b"first", "image/png")
        await store.put("k.png", b"second", "image/png")
        assert (await store.get("k.png"))[0] == b"second"


class TestAssetServiceOnMinio:
    async def test_generated_art_is_stored_and_addressable(self, bucket):
        repository = InMemoryAssetRepository()
        service = AssetService(
            repository, MinioAssetStore(), PlaceholderImageProvider(), enabled=True
        )
        spec = AssetSpec(kind="background", cache_key="bg_test_key", prompt="a rooftop at sunset")

        ref = await service.ensure(spec, "highschool_romance")

        assert ref.status is AssetStatus.ready
        assert ref.asset_id
        assert ref.url.startswith("http"), "MinIO should give a direct URL, not the proxy path"

        record = await repository.by_cache_key("bg_test_key")
        assert record.object_key == "backgrounds/bg_test_key.png"
        assert record.provider == "placeholder"
        assert record.size_bytes > 0

        data, content_type = await service.read(ref.asset_id)
        assert data[:8] == b"\x89PNG\r\n\x1a\n"
        assert content_type == "image/png"

    async def test_a_second_request_reuses_the_stored_object(self, bucket):
        """PRD §19 -- across a real store, not just the in-memory repository."""
        repository = InMemoryAssetRepository()
        calls = []

        class CountingProvider(PlaceholderImageProvider):
            name = "counting"

            async def generate(self, prompt, *, width=1024, height=576):
                calls.append(prompt)
                return await super().generate(prompt, width=width, height=height)

        service = AssetService(repository, MinioAssetStore(), CountingProvider(), enabled=True)
        spec = AssetSpec(kind="character", cache_key="ch_aiko_surprised", prompt="aiko, surprised")

        first = await service.ensure(spec, "w")
        second = await service.ensure(spec, "w")

        assert first.asset_id == second.asset_id
        assert len(calls) == 1, "the second request generated a new image instead of reusing one"

    async def test_a_reference_lookup_never_generates(self, bucket):
        """`reference` runs while a batch is being committed; it must not block on a model."""
        service = AssetService(
            InMemoryAssetRepository(), MinioAssetStore(), PlaceholderImageProvider(), enabled=True
        )
        ref = await service.reference(AssetSpec(kind="background", cache_key="cold", prompt="p"))

        assert ref.status is AssetStatus.pending
        assert ref.asset_id is None
