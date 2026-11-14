"""Test fixtures.

Everything runs on the offline seams -- no MongoDB, no MinIO, no API key -- which is the
same configuration a developer gets by cloning the repo and running ``uvicorn``.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Direct assignment, not setdefault: pydantic-settings ranks real environment variables
# above the ``.env`` file, and a developer's working copy commonly has WEB_MODE=True and
# a key in it. Inheritance made the suite fail for reasons the code under test had
# nothing to do with. Tests that need web mode pass it explicitly to ``Settings``.
os.environ["STORAGE_BACKEND"] = "memory"
os.environ["ASSET_BACKEND"] = "local"
os.environ["OPENROUTER_API_KEY"] = ""
os.environ["WEB_MODE"] = "False"
os.environ["IMAGE_GENERATION_ENABLED"] = "False"
os.environ["IMAGE_BACKEND"] = "openrouter"

from app.agents.director import DirectorAgent  # noqa: E402
from app.agents.safety import SafetyFilter  # noqa: E402
from app.agents.scripted import ScriptedNarrator  # noqa: E402
from app.agents.validator import Validator  # noqa: E402
from app.content import default_world  # noqa: E402
from app.domain.state import CharacterState, GameSession, PlayerProfile, WorldState  # noqa: E402


def _reachable(host: str, port: int, timeout: float = 0.75) -> bool:
    import socket

    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _endpoint(url: str, default_host: str, default_port: int) -> tuple[str, int]:
    """``(host, port)`` from a connection URL or a bare ``host:port`` string."""
    from urllib.parse import urlparse

    parsed = urlparse(url if "://" in url else f"//{url}")
    return parsed.hostname or default_host, parsed.port or default_port


def _configured_endpoints() -> tuple[str, str]:
    """Read the deployment's own Mongo/MinIO settings, so a non-default port works.

    The stack in ``docker-compose.yml`` publishes Mongo on ``MONGODB_PORT``, which a
    local ``.env`` may move (this repo runs it on 4533). Probing the hardcoded default
    skipped every integration test while a healthy MongoDB was running.
    """
    try:
        from app.config import Settings

        configured = Settings()
        return configured.MONGODB_URL, configured.MINIO_ENDPOINT
    except Exception:  # noqa: BLE001 - a broken config should still let offline tests run
        return "mongodb://localhost:27017", "localhost:9000"


MONGO_URL, _MINIO_ENDPOINT = _configured_endpoints()
MONGO_HOST, MONGO_PORT = _endpoint(MONGO_URL, "127.0.0.1", 27017)
MINIO_HOST, MINIO_PORT = _endpoint(_MINIO_ENDPOINT, "127.0.0.1", 9000)
MONGO_UP = _reachable(MONGO_HOST, MONGO_PORT)
MINIO_UP = _reachable(MINIO_HOST, MINIO_PORT)

#: Integration suites skip themselves rather than fail when the stack is down, so the
#: whole suite still runs on a machine with no Docker.
needs_mongo = pytest.mark.skipif(
    not MONGO_UP, reason="MongoDB not reachable - run `docker compose up -d mongodb`"
)
needs_minio = pytest.mark.skipif(
    not MINIO_UP, reason="MinIO not reachable - run `docker compose up -d minio`"
)


@pytest.fixture
def world():
    return default_world()


@pytest.fixture
def validator(world):
    return Validator(world=world, safety=SafetyFilter(), max_delta=5, max_steps=20)


@pytest.fixture
def narrator(world):
    return ScriptedNarrator(world)


@pytest.fixture
def director(world):
    return DirectorAgent(world)


@pytest.fixture
def session(world):
    return GameSession(
        id="test-game",
        world_id=world.id,
        player=PlayerProfile(name="Kai", pronouns="he/him"),
        world=WorldState(location="classroom", present_characters=["aiko", "ren"]),
        characters={
            character.id: CharacterState(
                id=character.id,
                name=character.name,
                relationship=dict(character.starting_relationship),
                current_emotion=character.default_emotion,
            )
            for character in world.characters
        },
    )


@pytest.fixture
def client(tmp_path, monkeypatch):
    """A live TestClient with a per-test asset directory."""
    from fastapi.testclient import TestClient

    from app.config import settings

    monkeypatch.setattr(settings, "STORAGE_BACKEND", "memory")
    monkeypatch.setattr(settings, "ASSET_BACKEND", "local")
    monkeypatch.setattr(settings, "LOCAL_ASSET_DIR", str(tmp_path / "assets"))
    monkeypatch.setattr(settings, "OPENROUTER_API_KEY", "")

    from app.main import app

    with TestClient(app) as test_client:
        yield test_client
