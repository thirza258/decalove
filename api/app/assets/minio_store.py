"""MinIO / S3-compatible asset store.

The ``minio`` client is synchronous, so every call is pushed to a worker thread to keep
the event loop free.
"""

from __future__ import annotations

import asyncio
import datetime
import io

from minio.error import S3Error

from app.assets.base import AssetStoreError
from app.config import settings
from app.storage import get_storage_client


class MinioAssetStore:
    name = "minio"

    def __init__(self, bucket: str | None = None, url_ttl_days: int = 7) -> None:
        self._bucket = bucket or settings.MINIO_BUCKET_NAME
        self._ttl = datetime.timedelta(days=url_ttl_days)

    async def put(self, key: str, data: bytes, content_type: str) -> None:
        def _put() -> None:
            get_storage_client().put_object(
                bucket_name=self._bucket,
                object_name=key,
                data=io.BytesIO(data),
                length=len(data),
                content_type=content_type,
            )

        try:
            await asyncio.to_thread(_put)
        except S3Error as exc:
            raise AssetStoreError(f"minio put failed for {key}: {exc}") from exc

    async def get(self, key: str) -> tuple[bytes, str]:
        def _get() -> tuple[bytes, str]:
            response = get_storage_client().get_object(self._bucket, key)
            try:
                return response.read(), response.headers.get("content-type", "image/png")
            finally:
                response.close()
                response.release_conn()

        try:
            return await asyncio.to_thread(_get)
        except S3Error as exc:
            raise AssetStoreError(f"minio get failed for {key}: {exc}") from exc

    async def exists(self, key: str) -> bool:
        def _stat() -> bool:
            try:
                get_storage_client().stat_object(self._bucket, key)
                return True
            except S3Error:
                return False

        return await asyncio.to_thread(_stat)

    async def url(self, key: str) -> str | None:
        def _url() -> str | None:
            try:
                return get_storage_client().presigned_get_object(self._bucket, key, expires=self._ttl)
            except S3Error:
                return None

        return await asyncio.to_thread(_url)
