"""In-memory repositories.

Not a test double -- the API genuinely runs on these when MongoDB is unreachable, which
is how the game is playable with no Docker. State is lost on restart, and the health
endpoint says so.
"""

from __future__ import annotations

from datetime import datetime, timezone

from app.domain.asset import AssetRecord
from app.domain.memory import MemoryRecord
from app.domain.state import GameSession
from app.repositories.base import StaleSessionError


def _as_utc(value: datetime) -> datetime:
    """Naive datetimes are treated as UTC.

    MongoDB hands back naive datetimes unless the client is built with ``tz_aware``, and
    comparing one to an aware ``cutoff`` raises rather than returning False -- which would
    take the sweeper down instead of skipping a row.
    """
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


class InMemoryGameRepository:
    name = "memory"

    def __init__(self) -> None:
        self._games: dict[str, GameSession] = {}
        self._versions: dict[str, int] = {}

    @staticmethod
    def _clone(session: GameSession) -> GameSession:
        """Isolate a session from the store without deep-copying its step ledger.

        Callers must never mutate stored state by accident -- the Mongo implementation
        would not let them, and the offline seam has to behave identically. But a blanket
        ``model_copy(deep=True)`` costs ~2.9 ms at 400 steps and runs on every read, which
        a long poll does ~33 times.

        ``StoryStep`` is frozen, so the steps can be shared behind a fresh list; only the
        mutable head is actually copied.
        """
        return session.model_copy(
            update={
                "player": session.player.model_copy(deep=True),
                "world": session.world.model_copy(deep=True),
                "characters": {
                    key: state.model_copy(deep=True) for key, state in session.characters.items()
                },
                "steps": list(session.steps),
                "history": list(session.history),
                "style": session.style.model_copy(deep=True),
                "pending": session.pending.model_copy(deep=True) if session.pending else None,
                "last_intent": (
                    session.last_intent.model_copy(deep=True) if session.last_intent else None
                ),
                "last_directive": (
                    session.last_directive.model_copy(deep=True) if session.last_directive else None
                ),
            }
        )

    async def create(self, session: GameSession) -> None:
        self._games[session.id] = self._clone(session)
        self._versions[session.id] = 0

    async def get(self, game_id: str) -> GameSession | None:
        stored = self._games.get(game_id)
        return self._clone(stored) if stored else None

    async def save(self, session: GameSession) -> None:
        if session.id not in self._games:
            raise StaleSessionError(f"game {session.id} does not exist")
        session.touch()
        self._games[session.id] = self._clone(session)
        self._versions[session.id] += 1

    async def delete(self, game_id: str) -> bool:
        self._versions.pop(game_id, None)
        return self._games.pop(game_id, None) is not None

    async def list_ids(self, limit: int = 50) -> list[str]:
        return list(self._games.keys())[:limit]

    async def delete_if_not_played_since(self, game_id: str, cutoff: datetime) -> bool:
        session = self._games.get(game_id)
        if session is None or session.ended or _as_utc(session.last_played_at) >= cutoff:
            return False
        return await self.delete(game_id)

    async def ids_not_played_since(self, cutoff: datetime, limit: int = 200) -> list[str]:
        stale = [
            game_id
            for game_id, session in self._games.items()
            if not session.ended and _as_utc(session.last_played_at) < cutoff
        ]
        return stale[:limit]


class InMemoryMemoryRepository:
    name = "memory"

    def __init__(self) -> None:
        self._records: list[MemoryRecord] = []

    async def add(self, record: MemoryRecord) -> None:
        self._records.append(record.model_copy(deep=True))

    async def for_game(self, game_id: str, character: str | None = None) -> list[MemoryRecord]:
        return [
            record.model_copy(deep=True)
            for record in self._records
            if record.game_id == game_id and (character is None or record.character == character)
        ]

    async def purge_game(self, game_id: str) -> int:
        before = len(self._records)
        self._records = [record for record in self._records if record.game_id != game_id]
        return before - len(self._records)


class InMemoryAssetRepository:
    name = "memory"

    def __init__(self) -> None:
        self._by_id: dict[str, AssetRecord] = {}
        self._by_key: dict[str, str] = {}

    async def by_cache_key(self, cache_key: str) -> AssetRecord | None:
        asset_id = self._by_key.get(cache_key)
        return self._by_id.get(asset_id) if asset_id else None

    async def get(self, asset_id: str) -> AssetRecord | None:
        return self._by_id.get(asset_id)

    async def put(self, record: AssetRecord) -> None:
        self._by_id[record.id] = record
        self._by_key[record.cache_key] = record.id
