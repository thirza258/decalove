"""MongoDB-backed repositories, against a real server.

Deliberately not a hand-rolled fake. The interesting behaviour here is the
optimistic-concurrency guard, and that depends on real ``find_one_and_update``
semantics -- a fake would only test my reimplementation of MongoDB.

Skips itself when MongoDB is not running.
"""

from __future__ import annotations

import uuid

import pytest
from motor.motor_asyncio import AsyncIOMotorClient

from conftest import needs_mongo
from app.domain.memory import MemoryRecord
from app.domain.asset import AssetRecord
from app.domain.state import CharacterState, GameSession, PlayerProfile, WorldState
from app.domain.story import GeneratedStep, RelationshipDelta, StoryStep
from app.repositories.base import StaleSessionError
from app.repositories.mongo_repo import (
    MongoAssetRepository,
    MongoGameRepository,
    MongoMemoryRepository,
)

pytestmark = [needs_mongo, pytest.mark.integration]

URL = "mongodb://root:rootpassword@localhost:27017"


@pytest.fixture
async def db():
    name = f"decalove_test_{uuid.uuid4().hex[:10]}"
    client = AsyncIOMotorClient(URL, serverSelectionTimeoutMS=3000)
    try:
        yield client[name]
    finally:
        await client.drop_database(name)
        client.close()


@pytest.fixture
async def games(db):
    repository = MongoGameRepository(db)
    await repository.ensure_indexes()
    return repository


def make_session(world, game_id="g1") -> GameSession:
    return GameSession(
        id=game_id,
        world_id=world.id,
        player=PlayerProfile(name="Kai", pronouns="he/him"),
        world=WorldState(location="classroom", present_characters=["aiko"]),
        characters={
            c.id: CharacterState(id=c.id, name=c.name, relationship=dict(c.starting_relationship))
            for c in world.characters
        },
    )


def make_step(index: int) -> StoryStep:
    return StoryStep(
        **GeneratedStep(
            type="narration",
            location="classroom",
            narration=f"Beat {index}.",
            relationship_changes={"aiko": RelationshipDelta(affection=1)},
        ).model_dump(),
        step_id=f"step_{index:05d}",
        index=index,
        batch_id="b1",
    )


class TestRoundTrip:
    async def test_a_session_survives_a_full_round_trip(self, games, world):
        original = make_session(world)
        original.steps.append(make_step(0))
        original.world.flags["met_aiko"] = True
        original.history.append("Kai arrived.")
        await games.create(original)

        loaded = await games.get("g1")
        assert loaded is not None
        assert loaded.id == "g1"
        assert loaded.player.name == "Kai"
        assert loaded.world.flags == {"met_aiko": True}
        assert loaded.characters["aiko"].relationship == original.characters["aiko"].relationship
        assert loaded.steps[0].step_id == "step_00000"
        assert loaded.steps[0].relationship_changes["aiko"].affection == 1
        assert loaded.steps[0].type is original.steps[0].type

    async def test_the_id_is_stored_as_the_mongo_primary_key(self, games, db, world):
        await games.create(make_session(world))
        document = await db["game_sessions"].find_one({"_id": "g1"})

        assert document is not None
        assert "id" not in document, "the domain id must not be duplicated alongside _id"
        assert document["_version"] == 0

    async def test_a_missing_game_returns_none(self, games):
        assert await games.get("does-not-exist") is None

    async def test_delete_reports_whether_anything_was_removed(self, games, world):
        await games.create(make_session(world))
        assert await games.delete("g1") is True
        assert await games.delete("g1") is False
        assert await games.get("g1") is None

    async def test_list_ids_is_newest_first_and_bounded(self, games, world):
        for index in range(5):
            await games.create(make_session(world, game_id=f"g{index}"))

        ids = await games.list_ids(limit=3)
        assert len(ids) == 3
        assert set(ids) <= {f"g{i}" for i in range(5)}


class TestOptimisticConcurrency:
    """The guard exists so a second process cannot silently overwrite a newer save."""

    async def test_saving_bumps_the_version(self, games, db, world):
        await games.create(make_session(world))
        session = await games.get("g1")

        session.steps.append(make_step(0))
        await games.save(session)
        assert (await db["game_sessions"].find_one({"_id": "g1"}))["_version"] == 1

        session.steps.append(make_step(1))
        await games.save(session)
        assert (await db["game_sessions"].find_one({"_id": "g1"}))["_version"] == 2

    async def test_a_stale_writer_is_rejected_rather_than_winning(self, games, world):
        await games.create(make_session(world))

        first = await games.get("g1")
        second = await games.get("g1")  # another process, same starting version

        first.history.append("first writer")
        await games.save(first)

        second.history.append("second writer")
        with pytest.raises(StaleSessionError, match="modified by another writer"):
            await games.save(second)

        survivor = await games.get("g1")
        assert survivor.history == ["first writer"], "the newer write was clobbered"

    async def test_the_same_handle_can_save_repeatedly(self, games, world):
        """A live session keeps working after a save -- the version must be refreshed."""
        await games.create(make_session(world))
        session = await games.get("g1")

        for index in range(4):
            session.steps.append(make_step(index))
            await games.save(session)

        assert len((await games.get("g1")).steps) == 4

    async def test_saving_a_deleted_game_says_so(self, games, world):
        await games.create(make_session(world))
        session = await games.get("g1")
        await games.delete("g1")

        with pytest.raises(StaleSessionError, match="does not exist"):
            await games.save(session)


class TestMemoryRepository:
    async def test_memories_round_trip_with_their_embeddings(self, db):
        repository = MongoMemoryRepository(db)
        await repository.ensure_indexes()

        await repository.add(
            MemoryRecord(
                id="m1",
                game_id="g1",
                character="aiko",
                text="Kai defended Aiko",
                importance=0.9,
                emotion="gratitude",
                impact={"trust": 3},
                embedding=[0.1, 0.2, 0.3],
                step_index=7,
            )
        )
        await repository.add(
            MemoryRecord(id="m2", game_id="g1", character="ren", text="Kai laughed")
        )
        await repository.add(
            MemoryRecord(id="m3", game_id="g2", character="aiko", text="different game")
        )

        everything = await repository.for_game("g1")
        assert {r.id for r in everything} == {"m1", "m2"}

        focused = await repository.for_game("g1", character="aiko")
        assert [r.id for r in focused] == ["m1"]
        assert focused[0].embedding == [0.1, 0.2, 0.3]
        assert focused[0].impact == {"trust": 3}
        assert focused[0].step_index == 7

    async def test_an_empty_game_has_no_memories(self, db):
        assert await MongoMemoryRepository(db).for_game("nobody") == []


class TestAssetRepository:
    async def test_lookup_by_cache_key_is_how_reuse_works(self, db):
        repository = MongoAssetRepository(db)
        await repository.ensure_indexes()

        record = AssetRecord(
            id="a1",
            cache_key="bg_rooftop_sunset",
            kind="background",
            world_id="highschool_romance",
            object_key="backgrounds/bg_rooftop_sunset.png",
            size_bytes=1234,
            prompt="a rooftop at sunset",
        )
        await repository.put(record)

        assert (await repository.by_cache_key("bg_rooftop_sunset")).id == "a1"
        assert (await repository.get("a1")).object_key == record.object_key
        assert await repository.by_cache_key("nothing") is None
        assert await repository.get("nothing") is None

    async def test_put_is_an_upsert(self, db):
        repository = MongoAssetRepository(db)
        base = {"id": "a1", "cache_key": "k", "object_key": "o"}

        await repository.put(AssetRecord(**base, size_bytes=1))
        await repository.put(AssetRecord(**base, size_bytes=2))

        assert (await repository.get("a1")).size_bytes == 2
        assert await db["generated_assets"].count_documents({}) == 1


class TestGarbageCollectionQueries:
    """The sweep query against a real server.

    Unit tests cover the policy with in-memory repositories; what they cannot cover is
    whether the MongoDB query filters correctly and whether the naive datetimes mongod
    hands back survive comparison against an aware cutoff.
    """

    @staticmethod
    def _aged(world, game_id, *, days: float, ended: bool = False):
        from datetime import timedelta

        session = make_session(world, game_id=game_id)
        session.last_played_at = session.last_played_at - timedelta(days=days)
        session.ended = ended
        return session

    async def test_it_finds_only_the_abandoned_games(self, games, world):
        from datetime import datetime, timedelta, timezone

        for game_id, days in (("old", 30), ("older", 90), ("fresh", 1)):
            await games.create(self._aged(world, game_id, days=days))

        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        stale = await games.ids_not_played_since(cutoff)

        assert set(stale) == {"old", "older"}
        assert "fresh" not in stale

    async def test_finished_stories_are_excluded_by_the_query_itself(self, games, world):
        from datetime import datetime, timedelta, timezone

        await games.create(self._aged(world, "abandoned", days=400))
        await games.create(self._aged(world, "finished", days=400, ended=True))

        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        assert await games.ids_not_played_since(cutoff) == ["abandoned"]

    async def test_results_are_oldest_first_and_bounded(self, games, world):
        from datetime import datetime, timedelta, timezone

        for index, days in enumerate((10, 40, 20, 90, 60)):
            await games.create(self._aged(world, f"g{index}", days=days))

        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        page = await games.ids_not_played_since(cutoff, limit=2)

        assert len(page) == 2
        assert page == ["g3", "g4"], "the longest-abandoned games should go first"

    async def test_the_timestamps_mongo_returns_still_compare(self, games, world):
        """mongod returns naive datetimes; comparing one to an aware cutoff raises."""
        from datetime import datetime, timedelta, timezone

        from app.services.maintenance import as_utc

        await games.create(self._aged(world, "old", days=30))
        loaded = await games.get("old")

        cutoff = datetime.now(timezone.utc) - timedelta(days=7)
        assert as_utc(loaded.last_played_at) < cutoff

    async def test_the_play_clock_survives_a_round_trip(self, games, world):
        """BSON stores datetimes at millisecond precision, so this loses sub-ms detail.
        Irrelevant against a seven-day TTL, but worth pinning so nobody later writes an
        exact-equality assertion and is confused by it."""
        from datetime import timedelta

        session = make_session(world)
        stamped = session.last_played_at
        await games.create(session)

        loaded = (await games.get("g1")).last_played_at.replace(tzinfo=None)
        assert abs(loaded - stamped.replace(tzinfo=None)) < timedelta(milliseconds=1)

    async def test_an_end_to_end_sweep_against_mongo(self, games, db, world):
        from datetime import timedelta

        from app.repositories.mongo_repo import MongoMemoryRepository
        from app.services.maintenance import MaintenanceService

        memories = MongoMemoryRepository(db)
        await memories.ensure_indexes()

        await games.create(self._aged(world, "abandoned", days=30))
        await games.create(self._aged(world, "finished", days=30, ended=True))
        await games.create(self._aged(world, "live", days=0))
        for owner in ("abandoned", "finished", "live"):
            await memories.add(
                MemoryRecord(id=f"{owner}-m", game_id=owner, character="aiko", text="x")
            )

        import asyncio

        class Locks:
            def __init__(self):
                self._locks = {}

            def lock(self, game_id):
                return self._locks.setdefault(game_id, asyncio.Lock())

        class Noop:
            def forget(self, game_id):
                pass

        service = MaintenanceService(
            games=games, memories=memories, generation=Locks(), game_service=Noop(), ttl_days=7
        )
        report = await service.sweep_once()

        assert report.deleted == 1
        assert report.game_ids == ["abandoned"]
        assert report.memories_removed == 1

        assert await games.get("abandoned") is None
        assert await games.get("finished") is not None
        assert await games.get("live") is not None
        assert await memories.for_game("abandoned") == []
        assert len(await memories.for_game("finished")) == 1
        assert len(await memories.for_game("live")) == 1

    async def test_the_sweep_index_exists(self, games, db):
        await games.ensure_indexes()
        indexes = await db["game_sessions"].index_information()
        keys = [tuple(spec["key"][0]) for spec in indexes.values() if spec.get("key")]

        assert ("last_played_at", 1) in keys
        assert not any(
            "expireAfterSeconds" in spec for spec in indexes.values()
        ), "a TTL index would delete sessions without cascading to their memories"
