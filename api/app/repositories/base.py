"""Repository protocols.

Nothing above this layer imports ``motor``. Swapping MongoDB for PostgreSQL (as PRD §5
originally suggested) means writing one more implementation, not touching the engine.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from app.domain.asset import AssetRecord
from app.domain.memory import MemoryRecord
from app.domain.state import GameSession


class StaleSessionError(RuntimeError):
    """Raised when a save would clobber a concurrent write.

    In-process writers are serialised by a per-game lock, so this only fires across
    processes -- which is exactly when losing a player's progress silently would be worst.
    """


@runtime_checkable
class GameRepository(Protocol):
    name: str

    async def create(self, session: GameSession) -> None: ...

    async def get(self, game_id: str) -> GameSession | None: ...

    async def save(self, session: GameSession) -> None: ...

    async def delete(self, game_id: str) -> bool: ...

    async def list_ids(self, limit: int = 50) -> list[str]: ...

    async def delete_if_not_played_since(self, game_id: str, cutoff: datetime) -> bool:
        """Delete only if the game is still expired. Returns whether it went.

        The per-game asyncio lock serialises this within one process. Across two API
        processes there is no shared lock, so the condition is re-asserted in the delete
        itself: a play that lands between the sweeper's re-check and its delete aborts the
        delete rather than losing the race.
        """
        ...

    async def ids_not_played_since(self, cutoff: datetime, limit: int = 200) -> list[str]:
        """Abandoned games: last played before ``cutoff``, and not finished.

        Finished stories are never returned. A player who got through 300 steps to reach
        an ending should not have that deleted a week later, and an ended session is a
        fixed-size document that does not grow.
        """
        ...


@runtime_checkable
class MemoryRepository(Protocol):
    name: str

    async def add(self, record: MemoryRecord) -> None: ...

    async def for_game(self, game_id: str, character: str | None = None) -> list[MemoryRecord]: ...

    async def purge_game(self, game_id: str) -> int:
        """Delete every memory belonging to a game. Returns how many went."""
        ...


@runtime_checkable
class AssetRepository(Protocol):
    name: str

    async def by_cache_key(self, cache_key: str) -> AssetRecord | None: ...

    async def get(self, asset_id: str) -> AssetRecord | None: ...

    async def put(self, record: AssetRecord) -> None: ...
