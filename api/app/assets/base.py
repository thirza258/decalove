"""Asset store protocol."""

from __future__ import annotations

from typing import Protocol, runtime_checkable


class AssetStoreError(RuntimeError):
    pass


@runtime_checkable
class AssetStore(Protocol):
    name: str

    async def put(self, key: str, data: bytes, content_type: str) -> None: ...

    async def get(self, key: str) -> tuple[bytes, str]: ...

    async def exists(self, key: str) -> bool: ...

    async def url(self, key: str) -> str | None:
        """A directly-fetchable URL, or ``None`` if the API must proxy the bytes."""
        ...
