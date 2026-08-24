"""Filesystem asset store.

The fallback that lets the game run with no MinIO and no Docker. Bytes are served back
through the API's own ``/assets/{id}/view`` route, so the Ren'Py client cannot tell the
difference.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

from app.assets.base import AssetStoreError


class LocalAssetStore:
    name = "local"

    def __init__(self, root: str | Path) -> None:
        self._root = Path(root)
        self._root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        safe = key.strip("/").replace("..", "_")
        path = self._root / safe
        # Defence in depth: never let a crafted key escape the asset root.
        if not path.resolve().is_relative_to(self._root.resolve()):
            raise AssetStoreError(f"illegal asset key: {key}")
        return path

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        def _write() -> None:
            path = self._path(key)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
            path.with_suffix(path.suffix + ".meta").write_text(
                json.dumps({"content_type": content_type})
            )

        await asyncio.to_thread(_write)

    async def get(self, key: str) -> tuple[bytes, str]:
        def _read() -> tuple[bytes, str]:
            path = self._path(key)
            if not path.exists():
                raise AssetStoreError(f"asset not found: {key}")
            meta_path = path.with_suffix(path.suffix + ".meta")
            content_type = "image/png"
            if meta_path.exists():
                try:
                    content_type = json.loads(meta_path.read_text()).get("content_type", content_type)
                except ValueError:
                    pass
            return path.read_bytes(), content_type

        return await asyncio.to_thread(_read)

    async def exists(self, key: str) -> bool:
        return await asyncio.to_thread(lambda: self._path(key).exists())

    async def url(self, key: str) -> str | None:
        return None  # served by the API proxy route
