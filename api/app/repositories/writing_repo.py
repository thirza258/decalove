"""Workspace metadata lives beside game saves in the existing MongoDB database."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Protocol

from pymongo import ReturnDocument


class WritingRepository(Protocol):
    async def ensure(self, workspace_id: str, data: dict) -> dict: ...
    async def get(self, workspace_id: str) -> dict | None: ...
    async def save(self, workspace_id: str, revision: int, data: dict) -> dict | None: ...
    async def put_file(self, record: dict) -> None: ...
    async def get_file(self, workspace_id: str, file_id: str) -> dict | None: ...


class MongoWritingRepository:
    def __init__(self, db: Any):
        self.workspaces = db["writing_workspaces"]
        self.files = db["writing_files"]

    async def ensure(self, workspace_id: str, data: dict) -> dict:
        return await self.workspaces.find_one_and_update(
            {"_id": workspace_id}, {"$setOnInsert": {"revision": 0, "data": data}},
            upsert=True, return_document=ReturnDocument.AFTER,
        )

    async def get(self, workspace_id: str) -> dict | None:
        return await self.workspaces.find_one({"_id": workspace_id})

    async def save(self, workspace_id: str, revision: int, data: dict) -> dict | None:
        return await self.workspaces.find_one_and_update(
            {"_id": workspace_id, "revision": revision},
            {"$set": {"data": data}, "$inc": {"revision": 1}}, return_document=ReturnDocument.AFTER,
        )

    async def put_file(self, record: dict) -> None:
        await self.files.update_one({"_id": record["_id"]}, {"$setOnInsert": record}, upsert=True)

    async def get_file(self, workspace_id: str, file_id: str) -> dict | None:
        return await self.files.find_one({"_id": file_id, "workspace_id": workspace_id})


class InMemoryWritingRepository:
    """Offline test/development seam, reported as temporary storage in the client."""

    def __init__(self):
        self.workspaces: dict[str, dict] = {}
        self.files: dict[str, dict] = {}

    async def ensure(self, workspace_id: str, data: dict) -> dict:
        self.workspaces.setdefault(workspace_id, {"_id": workspace_id, "revision": 0, "data": deepcopy(data)})
        return deepcopy(self.workspaces[workspace_id])

    async def get(self, workspace_id: str) -> dict | None:
        return deepcopy(self.workspaces.get(workspace_id))

    async def save(self, workspace_id: str, revision: int, data: dict) -> dict | None:
        current = self.workspaces.get(workspace_id)
        if current is None or current["revision"] != revision:
            return None
        current.update(revision=revision + 1, data=deepcopy(data))
        return deepcopy(current)

    async def put_file(self, record: dict) -> None:
        self.files[record["_id"]] = deepcopy(record)

    async def get_file(self, workspace_id: str, file_id: str) -> dict | None:
        record = self.files.get(file_id)
        return deepcopy(record) if record and record["workspace_id"] == workspace_id else None

