"""MongoDB drafts and MinIO manuscript exports, using the runtime's existing stores."""

import base64
import binascii
import hashlib
import json
from datetime import datetime, timezone

from app.assets.base import AssetStore
from app.models.writing_storage import (
    IMAGE_EXTENSIONS,
    IMAGE_TYPES,
    LIBRARY_PREFIX,
    MAX_IMAGE_BYTES,
    DocumentFileRequest,
    ImageUploadRequest,
    LibraryImageRequest,
    WorkspaceData,
    WorkspaceSave,
    WritingDocument,
    is_image,
)
from app.repositories.writing_repo import WritingRepository


class WorkspaceConflict(ValueError):
    pass


def dump(model) -> dict:
    """Stored exactly as the client sent it: absent optional fields stay absent, so a
    workspace saved by an older tab round-trips unchanged and idempotent retries match."""
    return model.model_dump(mode="json", exclude_none=True)


def image_label(alt: str) -> str:
    return alt.strip() or "untitled illustration"


def manuscript_text(doc: WritingDocument) -> str:
    """The plain-text manuscript. ``exportText`` in the client writes the same file."""
    passages = []
    list_number = 0
    for block in doc.blocks:
        prefix = ""
        if block.listStyle == "bullet":
            prefix = "• "
        elif block.listStyle == "number":
            list_number += 1
            prefix = f"{list_number}. "
        if block.kind == "image":
            caption = f"\n{block.text}" if block.text.strip() else ""
            passages.append(prefix + f"[Image: {image_label(block.image.alt)}]" + caption)
        elif block.kind != "dialogue":
            passages.append(prefix + block.text)
        elif doc.format == "script":
            passages.append(prefix + f"{block.speaker or 'CHARACTER'}: {block.text}")
        else:
            passages.append(prefix + f"“{block.text}”" + (f" — {block.speaker}" if block.speaker else ""))
    body = doc.title + "\n\n" + "\n\n".join(passages) + "\n"
    if not doc.storyboard:
        return body
    lines = ["STORYBOARD"]
    for index, panel in enumerate(doc.storyboard, 1):
        heading = f"{index}. {panel.shot.upper()}"
        if panel.title.strip():
            heading += f" — {panel.title}"
        lines.append(heading)
        if panel.description.strip():
            lines.append(f"   {panel.description}")
        if panel.dialogue.strip():
            lines.append(f"   “{panel.dialogue}”")
        if panel.notes.strip():
            lines.append(f"   Note: {panel.notes}")
        if panel.image is not None:
            lines.append(f"   [Image: {image_label(panel.image.alt)}]")
    return body + "\n" + "\n".join(lines) + "\n"


class WritingStorage:
    def __init__(self, repository: WritingRepository, store: AssetStore, *, backend: str):
        self.repository = repository
        self.store = store
        self.backend = backend

    def response(self, record: dict) -> dict:
        return {"id": record["_id"], "revision": record["revision"], "data": record["data"],
                "storage": self.backend, "files": self.store.name}

    async def open(self, workspace_id: str) -> dict:
        record = await self.repository.ensure(workspace_id, dump(WorkspaceData()))
        return self.response(record)

    async def save(self, workspace_id: str, request: WorkspaceSave) -> dict:
        data = dump(request.data)
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
            body = json.dumps({"version": 1, "document": dump(doc)}, ensure_ascii=False, indent=2)
            content_type = "application/json"
        else:
            body = manuscript_text(doc)
            content_type = "text/plain; charset=utf-8"
        payload = body.encode("utf-8")
        digest = hashlib.sha256(workspace_id.encode() + request.format.encode() + payload).hexdigest()
        key = f"writing/{workspace_id}/{doc.id}/{digest}.{request.format}"
        # Publish the metadata only once the object exists. Retrying writes identical bytes.
        await self.store.put(key, payload, content_type)
        await self.repository.put_file(self.record(digest, workspace_id, key, content_type,
                                                   request.format, len(payload), document_id=str(doc.id)))
        return {"id": digest, "format": request.format, "size": len(payload)}

    async def read_file(self, workspace_id: str, file_id: str) -> tuple[bytes, str] | None:
        record = await self.repository.get_file(workspace_id, file_id)
        if record is None or record.get("format") == "image":
            return None
        return await self.store.get(record["object_key"])

    # -- illustrations ------------------------------------------------------------
    #
    # Bytes live in the asset store beside the game's own art; the workspace keeps only
    # an identifier. A content-derived key makes an interrupted upload safe to retry,
    # and the same picture uploaded twice costs one object.

    def record(self, digest: str, workspace_id: str, key: str, content_type: str,
               file_format: str, size: int, *, document_id: str = "") -> dict:
        return {"_id": digest, "workspace_id": workspace_id, "document_id": document_id,
                "object_key": key, "content_type": content_type, "format": file_format,
                "created_at": datetime.now(timezone.utc).isoformat(), "size": size}

    async def create_image(self, workspace_id: str, request: ImageUploadRequest) -> dict:
        if await self.repository.get(workspace_id) is None:
            raise KeyError("Workspace not found")
        try:
            payload = base64.b64decode(request.data, validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("This picture could not be read. Try saving it again as PNG or JPEG.") from exc
        if not payload or len(payload) > MAX_IMAGE_BYTES:
            raise ValueError("Pictures are up to 5 MB. Export a smaller copy and insert that.")
        # The declared type is not evidence. A picture is what its first bytes say it is.
        if not is_image(payload, request.content_type):
            raise ValueError("This file is not a PNG, JPEG, WebP or GIF picture.")
        digest = hashlib.sha256(workspace_id.encode() + request.content_type.encode() + payload).hexdigest()
        key = f"writing/{workspace_id}/images/{digest}.{IMAGE_EXTENSIONS[request.content_type]}"
        await self.store.put(key, payload, request.content_type)
        await self.repository.put_file(self.record(digest, workspace_id, key, request.content_type,
                                                   "image", len(payload)))
        return {"id": digest, "content_type": request.content_type, "size": len(payload), "alt": request.alt}

    async def library(self, limit: int = 60) -> dict:
        """Pictures placed under ``writing/library/`` by hand -- see docs/IMAGES.md."""
        found = await self.store.list(LIBRARY_PREFIX, limit)
        pictures = [
            {"key": key, "name": key[len(LIBRARY_PREFIX):], "size": size}
            for key, size in found
            if key.rsplit(".", 1)[-1].lower() in {"png", "jpg", "jpeg", "webp", "gif"}
        ]
        return {"prefix": LIBRARY_PREFIX, "files": self.store.name, "pictures": pictures}

    async def adopt_image(self, workspace_id: str, request: LibraryImageRequest) -> dict:
        """Lets a workspace use a library picture without copying its bytes anywhere."""
        if await self.repository.get(workspace_id) is None:
            raise KeyError("Workspace not found")
        if not await self.store.exists(request.key):
            raise ValueError("That picture is no longer in the shared library.")
        extension = request.key.rsplit(".", 1)[-1].lower()
        content_type = "image/jpeg" if extension in ("jpg", "jpeg") else f"image/{extension}"
        digest = hashlib.sha256(workspace_id.encode() + b"library" + request.key.encode()).hexdigest()
        # Size 0: the object is referenced, not copied, and the store protocol has no stat.
        await self.repository.put_file(self.record(digest, workspace_id, request.key, content_type, "image", 0))
        return {"id": digest, "content_type": content_type, "size": 0,
                "alt": request.key[len(LIBRARY_PREFIX):].rsplit(".", 1)[0][:300]}

    async def read_image(self, workspace_id: str, image_id: str) -> tuple[bytes, str] | None:
        record = await self.repository.get_file(workspace_id, image_id)
        if record is None or record.get("format") != "image":
            return None
        data, _ = await self.store.get(record["object_key"])
        # Never echo a stored type back into a browser unchecked: this is inline content.
        declared = record["content_type"]
        return data, declared if declared in IMAGE_TYPES else "application/octet-stream"
