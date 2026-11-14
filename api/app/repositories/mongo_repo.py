"""MongoDB repositories.

Sessions carry a ``_version`` guard so a save from another process cannot silently
overwrite a newer one -- see ``StaleSessionError``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pymongo import ASCENDING, DESCENDING, ReturnDocument
from pymongo.errors import PyMongoError

from app.domain.asset import AssetRecord
from app.domain.chronicle import ChronicleEntry
from app.domain.knowledge import CharacterKnowledge
from app.domain.memory import MemoryRecord
from app.domain.state import GameSession
from app.domain.threads import NarrativeThread
from app.domain.trace import NarrativeTrace
from app.repositories.base import StaleSessionError

GAMES = "game_sessions"
MEMORIES = "character_memories"
ASSETS = "generated_assets"
CHRONICLE = "story_chronicle"
KNOWLEDGE = "character_knowledge"
THREADS = "narrative_threads"
TRACES = "narrative_traces"


def _dump(model: Any) -> dict[str, Any]:
    return model.model_dump(mode="python")


class MongoGameRepository:
    name = "mongo"

    def __init__(self, db: Any) -> None:
        self._db = db

    @property
    def _col(self) -> Any:
        return self._db[GAMES]

    async def ensure_indexes(self) -> None:
        await self._col.create_index([("_id", ASCENDING)])
        await self._col.create_index([("updated_at", ASCENDING)])
        # Plain ascending, deliberately NOT a TTL index: a TTL fires inside mongod and
        # cascades to nothing, so every purged save would leave its character_memories
        # behind forever with no owner left to find them by.
        await self._col.create_index([("last_played_at", ASCENDING)])

    async def create(self, session: GameSession) -> None:
        document = _dump(session)
        document["_id"] = document.pop("id")
        document["_version"] = 0
        await self._col.insert_one(document)

    async def get(self, game_id: str) -> GameSession | None:
        document = await self._col.find_one({"_id": game_id})
        if document is None:
            return None
        version = document.pop("_version", 0)
        document["id"] = document.pop("_id")
        session = GameSession.model_validate(document)
        # Stash the version on the instance so save() can guard on it without widening
        # the domain model with a persistence concern.
        object.__setattr__(session, "__mongo_version__", version)
        return session

    async def save(self, session: GameSession) -> None:
        session.touch()
        document = _dump(session)
        document.pop("id", None)
        expected = getattr(session, "__mongo_version__", None)
        query: dict[str, Any] = {"_id": session.id}
        if expected is not None:
            query["_version"] = expected

        try:
            updated = await self._col.find_one_and_update(
                query,
                {"$set": document, "$inc": {"_version": 1}},
                return_document=ReturnDocument.AFTER,
            )
        except PyMongoError as exc:  # pragma: no cover - needs a live server
            raise StaleSessionError(f"failed to save game {session.id}: {exc}") from exc

        if updated is None:
            if await self._col.find_one({"_id": session.id}, {"_id": 1}) is None:
                raise StaleSessionError(f"game {session.id} does not exist")
            raise StaleSessionError(
                f"game {session.id} was modified by another writer (expected version {expected})"
            )
        object.__setattr__(session, "__mongo_version__", updated.get("_version", 0))

    async def delete(self, game_id: str) -> bool:
        result = await self._col.delete_one({"_id": game_id})
        return result.deleted_count > 0

    async def list_ids(self, limit: int = 50) -> list[str]:
        cursor = self._col.find({}, {"_id": 1}).sort("updated_at", -1).limit(limit)
        return [document["_id"] async for document in cursor]

    async def delete_if_not_played_since(self, game_id: str, cutoff: datetime) -> bool:
        result = await self._col.delete_one(
            {"_id": game_id, "last_played_at": {"$lt": cutoff}, "ended": {"$ne": True}}
        )
        return result.deleted_count > 0

    async def ids_not_played_since(self, cutoff: datetime, limit: int = 200) -> list[str]:
        cursor = (
            self._col.find(
                {"last_played_at": {"$lt": cutoff}, "ended": {"$ne": True}}, {"_id": 1}
            )
            .sort("last_played_at", ASCENDING)
            .limit(limit)
        )
        return [document["_id"] async for document in cursor]


class MongoMemoryRepository:
    name = "mongo"

    def __init__(self, db: Any) -> None:
        self._db = db

    @property
    def _col(self) -> Any:
        return self._db[MEMORIES]

    async def ensure_indexes(self) -> None:
        await self._col.create_index([("game_id", ASCENDING), ("character", ASCENDING)])

    async def add(self, record: MemoryRecord) -> None:
        document = _dump(record)
        document["_id"] = document.pop("id")
        await self._col.update_one({"_id": document["_id"]}, {"$setOnInsert": document}, upsert=True)

    async def replace(self, record: MemoryRecord) -> None:
        document = _dump(record)
        document.pop("id", None)
        await self._col.update_one({"_id": record.id}, {"$set": document}, upsert=True)

    async def purge_game(self, game_id: str) -> int:
        result = await self._col.delete_many({"game_id": game_id})
        return result.deleted_count

    async def for_game(self, game_id: str, character: str | None = None) -> list[MemoryRecord]:
        query: dict[str, Any] = {"game_id": game_id}
        if character:
            query["character"] = character
        records = []
        async for document in self._col.find(query):
            document["id"] = document.pop("_id")
            records.append(MemoryRecord.model_validate(document))
        return records


class MongoChronicleRepository:
    name = "mongo"

    def __init__(self, db: Any) -> None:
        self._db = db

    @property
    def _col(self) -> Any:
        return self._db[CHRONICLE]

    async def ensure_indexes(self) -> None:
        # Read as "this game's story in order"; that is the only query there is.
        await self._col.create_index([("game_id", ASCENDING), ("index", ASCENDING)])

    async def note_attempt(self, game_id: str, batch_id: str, action: str) -> None:
        await self._col.update_one(
            {"_id": ChronicleEntry.key(game_id, batch_id)},
            {
                "$set": {"player_action": action},
                "$setOnInsert": {
                    "game_id": game_id, "batch_id": batch_id,
                    "created_at": datetime.now(timezone.utc),
                },
            },
            upsert=True,
        )

    async def record_scene(self, entry: ChronicleEntry) -> None:
        document = _dump(entry)
        document.pop("id", None)
        # Never $set player_action here: the attempt was written by whoever accepted the
        # turn, and a re-delivery arriving later must not blank it.
        created = document.pop("created_at")
        document.pop("player_action", None)
        await self._col.update_one(
            {"_id": entry.id}, {"$set": document, "$setOnInsert": {"created_at": created}}, upsert=True
        )

    async def for_game(self, game_id: str, limit: int = 200) -> list[ChronicleEntry]:
        # Newest first, then reversed: a story longer than the cap must lose its middle,
        # never its most recent scenes, which are the ones the next prompt needs most.
        cursor = self._col.find({"game_id": game_id}).sort("index", DESCENDING).limit(limit)
        entries = []
        async for document in cursor:
            document["id"] = document.pop("_id")
            entries.append(ChronicleEntry.model_validate(document))
        entries.reverse()
        return entries

    async def purge_game(self, game_id: str) -> int:
        result = await self._col.delete_many({"game_id": game_id})
        return result.deleted_count


class MongoAssetRepository:
    name = "mongo"

    def __init__(self, db: Any) -> None:
        self._db = db

    @property
    def _col(self) -> Any:
        return self._db[ASSETS]

    async def ensure_indexes(self) -> None:
        await self._col.create_index([("cache_key", ASCENDING)], unique=True)

    async def by_cache_key(self, cache_key: str) -> AssetRecord | None:
        document = await self._col.find_one({"cache_key": cache_key})
        return self._to_model(document)

    async def get(self, asset_id: str) -> AssetRecord | None:
        document = await self._col.find_one({"_id": asset_id})
        return self._to_model(document)

    async def put(self, record: AssetRecord) -> None:
        document = _dump(record)
        document.pop("id", None)
        await self._col.update_one({"_id": record.id}, {"$set": document}, upsert=True)

    @staticmethod
    def _to_model(document: dict[str, Any] | None) -> AssetRecord | None:
        if document is None:
            return None
        document["id"] = document.pop("_id")
        return AssetRecord.model_validate(document)


class _MongoScopedRepository:
    """Shared CRUD for the intelligence layer's per-game records.

    Two of these (knowledge, threads) are derived read models and one (traces) is
    diagnostic. None of them is load-bearing for delivery, so a Mongo outage here must
    surface as a logged warning rather than a failed turn -- callers already wrap them
    with bounded waits.
    """

    collection_name: str = ""
    model: type[Any] = object
    indexes: tuple[tuple[str, int], ...] = (("game_id", ASCENDING),)

    def __init__(self, db: Any) -> None:
        self._db = db

    @property
    def _col(self) -> Any:
        return self._db[self.collection_name]

    async def ensure_indexes(self) -> None:
        await self._col.create_index(list(self.indexes))

    async def upsert(self, record: Any) -> None:
        document = _dump(record)
        document.pop("id", None)
        await self._col.update_one({"_id": record.id}, {"$set": document}, upsert=True)

    async def purge_game(self, game_id: str) -> int:
        result = await self._col.delete_many({"game_id": game_id})
        return result.deleted_count

    async def _read(self, query: dict[str, Any], *, sort: list[tuple[str, int]] | None = None,
                    limit: int | None = None) -> list[Any]:
        cursor = self._col.find(query)
        if sort:
            cursor = cursor.sort(sort)
        if limit:
            cursor = cursor.limit(limit)
        records = []
        async for document in cursor:
            document["id"] = document.pop("_id")
            records.append(self.model.model_validate(document))
        return records


class MongoKnowledgeRepository(_MongoScopedRepository):
    name = "mongo"
    collection_name = KNOWLEDGE
    model = CharacterKnowledge
    indexes = (("game_id", ASCENDING), ("character_id", ASCENDING))

    async def for_game(
        self, game_id: str, character_id: str | None = None
    ) -> list[CharacterKnowledge]:
        query: dict[str, Any] = {"game_id": game_id}
        if character_id:
            query["character_id"] = character_id
        return await self._read(query, sort=[("created_at_step", ASCENDING)])


class MongoThreadRepository(_MongoScopedRepository):
    name = "mongo"
    collection_name = THREADS
    model = NarrativeThread
    indexes = (("game_id", ASCENDING), ("status", ASCENDING))

    async def for_game(self, game_id: str) -> list[NarrativeThread]:
        records = await self._read({"game_id": game_id})
        records.sort(key=lambda thread: (thread.status.value, -thread.priority))
        return records


class MongoTraceRepository(_MongoScopedRepository):
    name = "mongo"
    collection_name = TRACES
    model = NarrativeTrace
    indexes = (("game_id", ASCENDING), ("batch_id", ASCENDING))

    async def for_game(self, game_id: str, limit: int = 200) -> list[NarrativeTrace]:
        # Newest first, then reversed -- a long save must lose its oldest traces, never
        # the recent ones a regression report is about.
        records = await self._read(
            {"game_id": game_id}, sort=[("created_at", DESCENDING)], limit=limit
        )
        records.reverse()
        return records

    async def mark_delivered(self, game_id: str, batch_id: str, step_index: int) -> int:
        result = await self._col.update_many(
            {"game_id": game_id, "batch_id": batch_id},
            {"$set": {"delivered": True, "step_index": step_index}},
        )
        return result.modified_count
