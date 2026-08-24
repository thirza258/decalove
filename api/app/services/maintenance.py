"""Garbage collection of abandoned games.

A save the player has not continued for a week is deleted, along with the character
memories that belong to it. Generated art is deliberately left alone: assets are keyed by
a content-derived ``cache_key``, shared across every game in the world, and bounded by the
world's combinatorics rather than by how many sessions exist -- there is no per-game
subset of them to delete, and deleting one would only make the next player regenerate it.

Why an application sweeper rather than a MongoDB TTL index: a TTL fires inside mongod and
cascades to nothing, so every expired save would leave its memories behind with no owner
left to find them by. A TTL also does not exist on the in-memory backend, which would
break the offline seam and make the whole feature untestable without Docker.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from pydantic import BaseModel, Field

from app.repositories.base import GameRepository, MemoryRepository

log = logging.getLogger(__name__)


def as_utc(value: datetime) -> datetime:
    """Treat a naive datetime as UTC.

    MongoDB returns naive datetimes, and comparing one against an aware cutoff raises
    ``TypeError`` -- which would take the sweeper down rather than skip a row.
    """
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


class SweepReport(BaseModel):
    """What one sweep did. Returned for tests and logged for ops."""

    scanned: int = 0
    deleted: int = 0
    memories_removed: int = 0
    skipped: int = 0
    game_ids: list[str] = Field(default_factory=list)

    def __str__(self) -> str:  # pragma: no cover - log formatting
        return (
            f"scanned {self.scanned}, deleted {self.deleted} "
            f"({self.memories_removed} memories), skipped {self.skipped}"
        )


class MaintenanceService:
    def __init__(
        self,
        *,
        games: GameRepository,
        memories: MemoryRepository,
        generation,
        game_service,
        ttl_days: int = 7,
        interval_s: float = 3600.0,
        batch_limit: int = 200,
        enabled: bool = True,
    ) -> None:
        self.games = games
        self.memories = memories
        self.generation = generation
        self.game_service = game_service
        self.ttl = timedelta(days=ttl_days)
        self.interval_s = max(1.0, interval_s)
        self.batch_limit = max(1, batch_limit)
        self.enabled = enabled

        self._task: asyncio.Task[None] | None = None
        self._stopping = asyncio.Event()
        self.last_report: SweepReport | None = None
        self.last_swept_at: datetime | None = None

    # -- the sweep -----------------------------------------------------------------------

    def cutoff(self, now: datetime | None = None) -> datetime:
        return (now or datetime.now(timezone.utc)) - self.ttl

    async def sweep_once(self) -> SweepReport:
        """One pass. Safe to call directly; that is how it is tested."""
        cutoff = self.cutoff()
        candidates = await self.games.ids_not_played_since(cutoff, self.batch_limit)
        report = SweepReport(scanned=len(candidates))

        for game_id in candidates:
            # Every mutation of a session already goes through this lock, so taking it
            # means there is no interleaving at all between a purge and a delivery or a
            # generation batch committing.
            async with self.generation.lock(game_id):
                session = await self.games.get(game_id)
                if session is None:
                    continue
                # Re-check under the lock: the scan is not atomic, and a player who came
                # back between the query and here must not lose their save.
                if session.ended or as_utc(session.last_played_at) >= cutoff:
                    report.skipped += 1
                    continue

                # Guarded: the condition is re-asserted inside the delete, so a play
                # that lands between the re-check above and here aborts it. Memories are
                # only purged once the session is provably gone, which also makes the
                # session document the retry tombstone if the process dies here.
                if not await self.games.delete_if_not_played_since(game_id, cutoff):
                    report.skipped += 1
                    continue

                report.memories_removed += await self.memories.purge_game(game_id)
                report.deleted += 1
                report.game_ids.append(game_id)

            # Outside the lock: forget() pops the lock object itself.
            self.game_service.forget(game_id)

        self.last_report = report
        self.last_swept_at = datetime.now(timezone.utc)
        if report.deleted or report.skipped:
            log.info("session gc: %s", report)
        return report

    # -- lifecycle -----------------------------------------------------------------------

    def start(self) -> None:
        """Begin sweeping. Called from the app lifespan, not from ``build_runtime``.

        The task is intentionally NOT registered with ``GenerationService._tasks``: that
        set is what ``drain()`` waits on, and an endless loop in it would make every
        drain hang for its full timeout.
        """
        if not self.enabled or self._task is not None:
            return
        self._stopping.clear()
        self._task = asyncio.create_task(self._loop())
        log.info(
            "session gc armed: deleting games not played for %d day(s), every %.0f min",
            self.ttl.days,
            self.interval_s / 60,
        )

    async def stop(self) -> None:
        self._stopping.set()
        task, self._task = self._task, None
        if task is None:
            return
        task.cancel()
        try:
            await task
        except (asyncio.CancelledError, Exception):  # noqa: BLE001 - shutdown is best-effort
            pass

    async def _loop(self) -> None:
        while not self._stopping.is_set():
            try:
                await asyncio.wait_for(self._stopping.wait(), timeout=self.interval_s)
                return  # stop() was called
            except asyncio.TimeoutError:
                pass
            except asyncio.CancelledError:
                raise

            try:
                await self.sweep_once()
            except asyncio.CancelledError:
                raise
            except Exception:  # noqa: BLE001 - a bad sweep must not kill the sweeper
                log.exception("session gc sweep failed; will retry next interval")

    # -- observability -------------------------------------------------------------------

    def describe(self) -> dict:
        return {
            "enabled": self.enabled,
            "running": self._task is not None and not self._task.done(),
            "ttl_days": self.ttl.days,
            "interval_minutes": round(self.interval_s / 60, 1),
            "last_swept_at": self.last_swept_at.isoformat() if self.last_swept_at else None,
            "last_deleted": self.last_report.deleted if self.last_report else None,
        }
