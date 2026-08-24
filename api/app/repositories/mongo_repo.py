"""MongoDB repositories.

Sessions carry a ``_version`` guard so a save from another process cannot silently
overwrite a newer one -- see ``StaleSessionError``.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pymongo import ASCENDING, ReturnDocument
from pymongo.errors import PyMongoError

from app.domain.asset import AssetRecord
from app.domain.memory import MemoryRecord
from app.domain.state import GameSession
from app.repositories.base import StaleSessionError

GAMES = "game_sessions"
MEMORIES = "character_memories"
ASSETS = "generated_assets"


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
        await self._col.insert_one(document)

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
