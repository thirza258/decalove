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

os.environ.setdefault("STORAGE_BACKEND", "memory")
os.environ.setdefault("ASSET_BACKEND", "local")
os.environ.setdefault("OPENROUTER_API_KEY", "")

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


MONGO_UP = _reachable("127.0.0.1", 27017)
MINIO_UP = _reachable("127.0.0.1", 9000)

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
    return Validator(world=world, safety=SafetyFilter(), max_delta=5, max_steps=10)


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
