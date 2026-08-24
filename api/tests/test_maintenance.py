"""Garbage collection of abandoned games.

The requirement is "delete a story the player has not continued for a week". Most of
what follows is about the two ways that goes wrong: deleting a save somebody is still
playing, and failing to delete one nobody is.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from app.domain.memory import MemoryRecord
from app.domain.state import CharacterState, GameSession, PlayerProfile, WorldState
from app.repositories.memory_repo import InMemoryGameRepository, InMemoryMemoryRepository
from app.services.maintenance import MaintenanceService, as_utc

WEEK = timedelta(days=7)


def make_session(world, game_id: str, *, played_days_ago: float = 0.0, ended: bool = False):
    now = datetime.now(timezone.utc)
    return GameSession(
        id=game_id,
        world_id=world.id,
        player=PlayerProfile(name="Kai"),
        world=WorldState(location="classroom"),
        characters={
            c.id: CharacterState(id=c.id, name=c.name, relationship=dict(c.starting_relationship))
            for c in world.characters
        },
        ended=ended,
        last_played_at=now - timedelta(days=played_days_ago),
    )


class Bench:
    """A maintenance service over in-memory repositories."""

    def __init__(self, ttl_days: int = 7):
        self.games = InMemoryGameRepository()
        self.memories = InMemoryMemoryRepository()
        self.forgotten: list[str] = []

        bench = self

        class Locks:
            def __init__(self):
                self._locks: dict[str, asyncio.Lock] = {}

            def lock(self, game_id):
                return self._locks.setdefault(game_id, asyncio.Lock())

            def forget(self, game_id):
                self._locks.pop(game_id, None)

        class Service:
            def forget(self, game_id):
                bench.forgotten.append(game_id)

        self.generation = Locks()
        self.service = MaintenanceService(
            games=self.games,
            memories=self.memories,
            generation=self.generation,
            game_service=Service(),
            ttl_days=ttl_days,
            interval_s=3600,
        )

    async def add(self, world, game_id, *, played_days_ago=0.0, ended=False, memories=0):
        await self.games.create(
            make_session(world, game_id, played_days_ago=played_days_ago, ended=ended)
        )
        for index in range(memories):
            await self.memories.add(
                MemoryRecord(id=f"{game_id}-m{index}", game_id=game_id, character="aiko", text="x")
            )


class TestWhatGetsCollected:
    async def test_a_game_abandoned_for_over_a_week_is_deleted(self, world):
        bench = Bench()
        await bench.add(world, "old", played_days_ago=8, memories=3)

        report = await bench.service.sweep_once()

        assert report.deleted == 1
        assert report.game_ids == ["old"]
        assert report.memories_removed == 3
        assert await bench.games.get("old") is None
        assert await bench.memories.for_game("old") == []

    async def test_a_game_played_yesterday_is_left_alone(self, world):
        bench = Bench()
        await bench.add(world, "fresh", played_days_ago=1, memories=2)

        report = await bench.service.sweep_once()

        assert report.deleted == 0
        assert await bench.games.get("fresh") is not None
        assert len(await bench.memories.for_game("fresh")) == 2

    async def test_a_finished_story_is_never_collected(self, world):
        """Someone got through 300 steps to reach that ending."""
        bench = Bench()
        await bench.add(world, "finished", played_days_ago=400, ended=True)

        report = await bench.service.sweep_once()

        assert report.deleted == 0
        assert await bench.games.get("finished") is not None

    async def test_only_the_abandoned_game_loses_its_memories(self, world):
        bench = Bench()
        await bench.add(world, "old", played_days_ago=9, memories=2)
        await bench.add(world, "live", played_days_ago=0, memories=4)

        await bench.service.sweep_once()

        assert await bench.memories.for_game("old") == []
        assert len(await bench.memories.for_game("live")) == 4

    async def test_the_boundary_is_the_ttl(self, world):
        bench = Bench(ttl_days=7)
        await bench.add(world, "just_inside", played_days_ago=6.9)
        await bench.add(world, "just_outside", played_days_ago=7.1)

        report = await bench.service.sweep_once()

        assert report.game_ids == ["just_outside"]

    async def test_a_shorter_ttl_collects_more(self, world):
        bench = Bench(ttl_days=1)
        await bench.add(world, "two_days", played_days_ago=2)
        assert (await bench.service.sweep_once()).deleted == 1

    async def test_a_sweep_with_nothing_to_do_is_quiet(self, world):
        bench = Bench()
        await bench.add(world, "fresh", played_days_ago=0)
        report = await bench.service.sweep_once()
        assert (report.scanned, report.deleted, report.skipped) == (0, 0, 0)

    async def test_the_scan_is_bounded(self, world):
        bench = Bench()
        bench.service.batch_limit = 3
        for index in range(10):
            await bench.add(world, f"old{index}", played_days_ago=30)

        report = await bench.service.sweep_once()

        assert report.deleted == 3, "one sweep must not stall the loop on a huge backlog"
        assert (await bench.service.sweep_once()).deleted == 3, "the rest go next time"


class TestRaces:
    async def test_a_player_who_came_back_between_scan_and_delete_keeps_their_save(self, world):
        """The scan is not atomic. The re-check under the lock is what makes it safe."""
        bench = Bench()
        await bench.add(world, "returning", played_days_ago=0)

        async def pretend_stale(cutoff, limit=200):
            return ["returning"]

        bench.games.ids_not_played_since = pretend_stale

        report = await bench.service.sweep_once()

        assert report.deleted == 0
        assert report.skipped == 1
        assert await bench.games.get("returning") is not None

    async def test_a_game_deleted_underneath_the_sweep_is_not_an_error(self, world):
        bench = Bench()

        async def ghost(cutoff, limit=200):
            return ["never-existed"]

        bench.games.ids_not_played_since = ghost
        report = await bench.service.sweep_once()
        assert (report.scanned, report.deleted) == (1, 0)

    async def test_per_game_bookkeeping_is_dropped_with_the_save(self, world):
        """Otherwise the lock table is a slow leak keyed by every game id ever seen."""
        bench = Bench()
        await bench.add(world, "old", played_days_ago=30)
        bench.generation.lock("old")

        await bench.service.sweep_once()

        assert bench.forgotten == ["old"]

    async def test_naive_timestamps_from_mongo_do_not_crash_the_sweep(self, world):
        """MongoDB returns naive datetimes; comparing one to an aware cutoff raises."""
        bench = Bench()
        await bench.add(world, "old", played_days_ago=30)
        stored = bench.games._games["old"]
        stored.last_played_at = stored.last_played_at.replace(tzinfo=None)

        report = await bench.service.sweep_once()
        assert report.deleted == 1

    def test_as_utc_assumes_utc_for_naive_values(self):
        naive = datetime(2026, 1, 1, 12, 0, 0)
        assert as_utc(naive).tzinfo is timezone.utc
        aware = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
        assert as_utc(aware) is aware


class TestTheLoop:
    async def test_start_and_stop_are_clean(self, world):
        bench = Bench()
        bench.service.interval_s = 0.05
        bench.service.start()
        assert bench.service.describe()["running"] is True

        await asyncio.sleep(0.15)
        await bench.service.stop()

        assert bench.service.describe()["running"] is False
        assert bench.service.last_swept_at is not None, "it should have swept at least once"

    async def test_stopping_something_that_never_started_is_fine(self, world):
        await Bench().service.stop()

    async def test_starting_twice_does_not_double_up(self, world):
        bench = Bench()
        bench.service.interval_s = 3600
        bench.service.start()
        first = bench.service._task
        bench.service.start()
        assert bench.service._task is first
        await bench.service.stop()

    async def test_disabled_means_no_task_at_all(self, world):
        bench = Bench()
        bench.service.enabled = False
        bench.service.start()
        assert bench.service._task is None
        assert bench.service.describe()["enabled"] is False

    async def test_a_failing_sweep_does_not_kill_the_sweeper(self, world):
        bench = Bench()
        bench.service.interval_s = 0.03
        calls = []

        async def explode():
            calls.append(1)
            raise RuntimeError("mongo went away")

        bench.service.sweep_once = explode
        bench.service.start()
        await asyncio.sleep(0.15)
        await bench.service.stop()

        assert len(calls) >= 2, "the loop gave up after the first failure"


class TestObservability:
    async def test_health_reports_the_collector(self, client):
        gc = client.get("/health").json()["session_gc"]

        assert gc["ttl_days"] == 7
        assert gc["enabled"] is True
        assert "interval_minutes" in gc

    async def test_describe_records_the_last_sweep(self, world):
        bench = Bench()
        await bench.add(world, "old", played_days_ago=30)
        assert bench.service.describe()["last_swept_at"] is None

        await bench.service.sweep_once()
        described = bench.service.describe()

        assert described["last_swept_at"] is not None
        assert described["last_deleted"] == 1


class TestPlayClock:
    """`last_played_at` must track the player, not the engine."""

    def test_delivering_a_step_counts_as_playing(self, client):
        import time

        game_id = client.post("/api/v1/games", json={"player_name": "Kai"}).json()["game_id"]
        repository = client.app.state.runtime.games

        async def played_at():
            return (await repository.get(game_id)).last_played_at

        before = asyncio.run(played_at())
        time.sleep(0.01)
        client.get(f"/api/v1/games/{game_id}/steps/next", params={"wait_ms": 2000})

        assert asyncio.run(played_at()) > before

    def test_reading_the_state_does_not_count_as_playing(self, client):
        game_id = client.post("/api/v1/games", json={"player_name": "Kai"}).json()["game_id"]
        repository = client.app.state.runtime.games

        async def played_at():
            return (await repository.get(game_id)).last_played_at

        before = asyncio.run(played_at())
        for _ in range(3):
            client.get(f"/api/v1/games/{game_id}")
            client.get(f"/api/v1/games/{game_id}/save")

        assert asyncio.run(played_at()) == before, (
            "a monitoring script polling state would otherwise keep every save alive"
        )

    def test_background_writes_do_not_count_as_playing(self, client):
        """The failure this guards: an asset back-fill landing days after the player
        quit, resetting the clock and making the save immortal."""
        game_id = client.post("/api/v1/games", json={"player_name": "Kai"}).json()["game_id"]
        repository = client.app.state.runtime.games

        async def snapshot():
            session = await repository.get(game_id)
            return session.last_played_at, session.updated_at

        played_before, _ = asyncio.run(snapshot())

        async def background_write():
            session = await repository.get(game_id)
            session.history.append("a batch finished long after everyone left")
            await repository.save(session)

        asyncio.run(background_write())
        played_after, updated_after = asyncio.run(snapshot())

        assert played_after == played_before, "a background write reset the play clock"
        assert updated_after > played_after, "updated_at should still have moved"


class TestARequestInFlight:
    """The window the sweeper's under-lock re-check does not cover on its own.

    `submit_action` parses intent before it takes the lock, and with an API key that
    parse is a multi-second model call. A player returning after eight days sits in that
    window with a save the collector still considers abandoned.
    """

    def test_typing_a_line_stamps_the_play_clock_before_the_slow_parse(self, client, monkeypatch):
        import asyncio

        runtime = client.app.state.runtime
        game_id = client.post("/api/v1/games", json={"player_name": "Kai"}).json()["game_id"]
        repository = runtime.games

        async def backdate():
            session = await repository.get(game_id)
            session.last_played_at = session.last_played_at - timedelta(days=8)
            await repository.save(session)

        asyncio.run(backdate())

        seen: dict[str, datetime] = {}
        original = runtime.game_service.director.parse

        async def slow_parse(session, text):
            # Stands in for the OpenRouter round trip. By the time the parse runs, the
            # play clock must already say the player is back.
            stored = await repository.get(game_id)
            seen["at_parse_time"] = stored.last_played_at
            return await original(session, text)

        monkeypatch.setattr(runtime.game_service.director, "parse", slow_parse)
        client.post(f"/api/v1/games/{game_id}/actions", json={"input": "I say hello"})

        assert seen["at_parse_time"] > datetime.now(timezone.utc) - timedelta(minutes=1), (
            "the save was still a collection candidate while the player's request was in flight"
        )

    def test_a_save_deleted_underneath_a_request_answers_404_not_202(self, client, monkeypatch):
        """A cheerful 202 with a null batch id tells the player their line landed when it
        did not, and the next poll 404s anyway."""
        import asyncio

        runtime = client.app.state.runtime
        game_id = client.post("/api/v1/games", json={"player_name": "Kai"}).json()["game_id"]

        original = runtime.game_service.director.parse

        async def parse_then_vanish(session, text):
            intent = await original(session, text)
            await runtime.games.delete(game_id)
            return intent

        monkeypatch.setattr(runtime.game_service.director, "parse", parse_then_vanish)
        response = client.post(f"/api/v1/games/{game_id}/actions", json={"input": "I say hello"})

        assert response.status_code == 404, f"got {response.status_code}: {response.text}"

    async def test_the_delete_itself_re_asserts_the_condition(self, world):
        """Two API processes share MongoDB but not the asyncio lock, so the guard has to
        live in the delete rather than only in the read before it."""
        bench = Bench()
        await bench.add(world, "returning", played_days_ago=0)

        cutoff = bench.service.cutoff()
        assert await bench.games.delete_if_not_played_since("returning", cutoff) is False
        assert await bench.games.get("returning") is not None

        await bench.add(world, "abandoned", played_days_ago=30)
        assert await bench.games.delete_if_not_played_since("abandoned", cutoff) is True
        assert await bench.games.get("abandoned") is None

    async def test_a_finished_story_survives_the_guarded_delete(self, world):
        bench = Bench()
        await bench.add(world, "finished", played_days_ago=400, ended=True)
        assert await bench.games.delete_if_not_played_since("finished", bench.service.cutoff()) is False

    async def test_memories_are_only_purged_once_the_session_is_gone(self, world, monkeypatch):
        """The session document is the retry tombstone: purging memories first and then
        losing the delete would orphan them with no owner left to find them by."""
        bench = Bench()
        await bench.add(world, "contested", played_days_ago=30, memories=3)

        async def lost_the_race(game_id, cutoff):
            return False

        bench.games.delete_if_not_played_since = lost_the_race
        report = await bench.service.sweep_once()

        assert report.deleted == 0
        assert report.skipped == 1
        assert len(await bench.memories.for_game("contested")) == 3
