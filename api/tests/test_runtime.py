"""The composition root — which implementation each seam resolves to.

Every dependency is probed rather than assumed, so these tests pin the probe
outcomes explicitly instead of depending on whether MongoDB happens to be running
on the machine.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from app.assets.local_store import LocalAssetStore
from app.assets.minio_store import MinioAssetStore
from app.config import Settings
from app.llm.embeddings import HashingEmbedding, HttpEmbedding
from app.llm.openrouter import OpenRouterChat, OpenRouterImage
from app.llm.placeholder_image import PlaceholderImageProvider
from app.repositories.memory_repo import InMemoryGameRepository
from app.runtime import _build_asset_store, _build_persistence, _build_providers, build_runtime


def settings(**overrides) -> Settings:
    base = {
        "STORAGE_BACKEND": "memory",
        "ASSET_BACKEND": "local",
        "OPENROUTER_API_KEY": "",
        "EMBEDDING_API_KEY": "",
    }
    base.update(overrides)
    return Settings(**base)


@pytest.fixture
def mongo_down(monkeypatch):
    async def unreachable(*args, **kwargs):
        return False

    monkeypatch.setattr("app.runtime.try_connect", unreachable)


@pytest.fixture
def minio_down(monkeypatch):
    monkeypatch.setattr("app.runtime.init_minio", lambda: False)


class TestPersistenceSelection:
    async def test_memory_is_chosen_without_probing_mongo(self, monkeypatch):
        probed = []

        async def probe(*args, **kwargs):
            probed.append(1)
            return True

        monkeypatch.setattr("app.runtime.try_connect", probe)
        games, _, _, backend = await _build_persistence(settings(STORAGE_BACKEND="memory"))

        assert backend == "memory"
        assert isinstance(games, InMemoryGameRepository)
        assert probed == [], "STORAGE_BACKEND=memory should not touch MongoDB at all"

    async def test_auto_falls_back_when_mongo_is_unreachable(self, mongo_down):
        _, _, _, backend = await _build_persistence(settings(STORAGE_BACKEND="auto"))
        assert backend == "memory"

    async def test_requiring_mongo_fails_loudly_rather_than_losing_saves(self, mongo_down):
        with pytest.raises(RuntimeError) as error:
            await _build_persistence(settings(STORAGE_BACKEND="mongo"))

        message = str(error.value)
        assert "docker compose up -d" in message, "the error should say how to fix it"
        assert "STORAGE_BACKEND=memory" in message


class TestAssetStoreSelection:
    def test_local_is_chosen_without_probing_minio(self, monkeypatch, tmp_path):
        monkeypatch.setattr("app.runtime.init_minio", lambda: pytest.fail("probed MinIO"))
        store, backend = _build_asset_store(settings(LOCAL_ASSET_DIR=str(tmp_path)))
        assert backend == "local"
        assert isinstance(store, LocalAssetStore)

    def test_auto_falls_back_when_minio_is_unreachable(self, minio_down, tmp_path):
        _, backend = _build_asset_store(
            settings(ASSET_BACKEND="auto", LOCAL_ASSET_DIR=str(tmp_path))
        )
        assert backend == "local"

    def test_requiring_minio_fails_loudly(self, minio_down):
        with pytest.raises(RuntimeError, match="docker compose up -d"):
            _build_asset_store(settings(ASSET_BACKEND="minio"))

    def test_minio_is_used_when_it_is_up(self, monkeypatch):
        monkeypatch.setattr("app.runtime.init_minio", lambda: True)
        store, backend = _build_asset_store(settings(ASSET_BACKEND="auto"))
        assert backend == "minio"
        assert isinstance(store, MinioAssetStore)

    def test_a_relative_asset_dir_resolves_under_the_api_package(self):
        """Relative paths must not depend on the process working directory."""
        store, _ = _build_asset_store(settings(LOCAL_ASSET_DIR="var/test-assets"))
        root = store._root

        assert root.is_absolute()
        assert root.name == "test-assets"
        assert Path(__file__).resolve().parent.parent == root.parent.parent, (
            f"resolved to {root}, outside the api directory"
        )

        root.rmdir()
        if not any(root.parent.iterdir()):
            root.parent.rmdir()


class TestProviderSelection:
    def test_without_a_key_there_is_no_chat_provider(self):
        chat, image, embedder = _build_providers(settings())

        assert chat is None, "the scripted narrator handles this case, not a fake provider"
        assert isinstance(image, PlaceholderImageProvider)
        assert isinstance(embedder, HashingEmbedding)

    def test_a_key_wires_openrouter_for_chat_only(self):
        chat, image, _ = _build_providers(settings(OPENROUTER_API_KEY="sk-x"))

        assert isinstance(chat, OpenRouterChat)
        assert isinstance(image, PlaceholderImageProvider), "images cost money; stay off by default"

    def test_images_need_both_a_key_and_the_flag(self):
        _, image, _ = _build_providers(
            settings(OPENROUTER_API_KEY="sk-x", IMAGE_GENERATION_ENABLED=True)
        )
        assert isinstance(image, OpenRouterImage)

        _, image, _ = _build_providers(settings(IMAGE_GENERATION_ENABLED=True))
        assert isinstance(image, PlaceholderImageProvider), (
            "the flag alone must still leave the pipeline exercisable offline"
        )

    def test_attribution_headers_are_passed_through(self):
        chat, _, _ = _build_providers(
            settings(
                OPENROUTER_API_KEY="sk-x",
                OPENROUTER_SITE_URL="https://decalove.example",
                OPENROUTER_APP_NAME="Decalove",
            )
        )
        headers = chat._headers()
        assert headers["HTTP-Referer"] == "https://decalove.example"
        assert headers["X-Title"] == "Decalove"

    def test_http_embeddings_need_a_key_too(self):
        _, _, embedder = _build_providers(
            settings(EMBEDDING_BACKEND="http", EMBEDDING_API_KEY="sk-e")
        )
        assert isinstance(embedder, HttpEmbedding)

        _, _, embedder = _build_providers(settings(EMBEDDING_BACKEND="http"))
        assert isinstance(embedder, HashingEmbedding), "no key should not mean no embeddings"

    def test_embedding_dimensions_are_honoured(self):
        _, _, embedder = _build_providers(settings(EMBEDDING_DIMENSIONS=64))
        assert embedder.dimensions == 64


class TestRuntimeAssembly:
    async def test_a_fully_offline_runtime_describes_itself_honestly(self, tmp_path, mongo_down, minio_down):
        runtime = await build_runtime(settings(STORAGE_BACKEND="auto", ASSET_BACKEND="auto", LOCAL_ASSET_DIR=str(tmp_path)))
        try:
            description = runtime.describe()
            assert description["storage"] == "memory"
            assert description["assets"] == "local"
            assert "scripted" in description["narrative"]
            assert description["images"] == "disabled"
            assert description["embeddings"] == "hashing"
            assert description["world"] == "highschool_romance"
        finally:
            await runtime.close()

    async def test_closing_shuts_down_generation_and_providers(self, tmp_path, mongo_down, minio_down):
        runtime = await build_runtime(
            settings(OPENROUTER_API_KEY="sk-x", LOCAL_ASSET_DIR=str(tmp_path))
        )
        chat = runtime.chat
        await chat._http()  # force a client into existence
        assert chat._client is not None

        await runtime.close()
        assert chat._client is None
        assert not [t for t in runtime.generation._tasks if not t.done()]

    async def test_the_engine_shares_one_narrative_agent(self, tmp_path, mongo_down, minio_down):
        """Patching it in one place must affect the whole engine."""
        runtime = await build_runtime(settings(LOCAL_ASSET_DIR=str(tmp_path)))
        try:
            assert runtime.generation.narrative is runtime.game_service.narrative
            assert runtime.generation.games is runtime.games
        finally:
            await runtime.close()


class TestSettings:
    def test_has_llm_ignores_whitespace(self):
        assert Settings(OPENROUTER_API_KEY="   ").has_llm is False
        assert Settings(OPENROUTER_API_KEY="sk-x").has_llm is True

    def test_unknown_environment_variables_do_not_break_startup(self, monkeypatch):
        monkeypatch.setenv("SOMETHING_ELSE_ENTIRELY", "1")
        assert Settings().PROJECT_NAME
