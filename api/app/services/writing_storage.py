"""MongoDB drafts and MinIO manuscript exports, using the runtime's existing stores."""

import hashlib
import json
from datetime import datetime, timezone

from app.assets.base import AssetStore
from app.models.writing_storage import DocumentFileRequest, WorkspaceData, WorkspaceSave
from app.repositories.writing_repo import WritingRepository


class WorkspaceConflict(ValueError):
    pass


class WritingStorage:
    def __init__(self, repository: WritingRepository, store: AssetStore, *, backend: str):
        self.repository = repository
        self.store = store
        self.backend = backend

    def response(self, record: dict) -> dict:
        return {"id": record["_id"], "revision": record["revision"], "data": record["data"],
                "storage": self.backend, "files": self.store.name}

    async def open(self, workspace_id: str) -> dict:
        record = await self.repository.ensure(workspace_id, WorkspaceData().model_dump(mode="json"))
        return self.response(record)

    async def save(self, workspace_id: str, request: WorkspaceSave) -> dict:
        data = request.data.model_dump(mode="json")
        record = await self.repository.save(workspace_id, request.revision, data)
        if record is None:
            current = await self.repository.get(workspace_id)
            # A lost response is safe to retry when its exact content already committed.
            if current and current["data"] == data:
                return self.response(current)
            raise WorkspaceConflict("This workspace changed in another tab. Export your unsaved draft before reloading.")
        return self.response(record)

    async def create_file(self, workspace_id: str, request: DocumentFileRequest) -> dict:
        if await self.repository.get(workspace_id) is None:
            raise KeyError("Workspace not found")
        doc = request.document
        if request.format == "json":
            body = json.dumps({"version": 1, "document": doc.model_dump(mode="json")}, ensure_ascii=False, indent=2)
            content_type = "application/json"
        else:
            passages = []
            list_number = 0
            for block in doc.blocks:
                prefix = ""
                if block.listStyle == "bullet":
                    prefix = "• "
                elif block.listStyle == "number":
                    list_number += 1
                    prefix = f"{list_number}. "
                if block.kind != "dialogue":
                    passages.append(prefix + block.text)
                elif doc.format == "script":
                    passages.append(prefix + f"{block.speaker or 'CHARACTER'}: {block.text}")
                else:
                    passages.append(prefix + f"“{block.text}”" + (f" — {block.speaker}" if block.speaker else ""))
            body = doc.title + "\n\n" + "\n\n".join(passages) + "\n"
            content_type = "text/plain; charset=utf-8"
        payload = body.encode("utf-8")
        digest = hashlib.sha256(workspace_id.encode() + request.format.encode() + payload).hexdigest()
        key = f"writing/{workspace_id}/{doc.id}/{digest}.{request.format}"
        # Publish the metadata only once the object exists. Retrying writes identical bytes.
        await self.store.put(key, payload, content_type)
        record = {"_id": digest, "workspace_id": workspace_id, "document_id": str(doc.id),
                  "object_key": key, "content_type": content_type, "format": request.format,
                  "created_at": datetime.now(timezone.utc).isoformat(), "size": len(payload)}
        await self.repository.put_file(record)
        return {"id": digest, "format": request.format, "size": len(payload)}

    async def read_file(self, workspace_id: str, file_id: str) -> tuple[bytes, str] | None:
        record = await self.repository.get_file(workspace_id, file_id)
        if record is None:
            return None
        return await self.store.get(record["object_key"])
