import logging
import socket

from minio import Minio
from minio.error import S3Error
from urllib3.exceptions import HTTPError

from app.config import settings

log = logging.getLogger(__name__)


class Storage:
    client: Minio = None
    available: bool = False


storage = Storage()

def get_storage_client():
    if storage.client is None:
        storage.client = Minio(
            settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=settings.MINIO_SECURE
        )
    return storage.client

def _reachable(endpoint: str, timeout: float = 0.6) -> bool:
    """Fast TCP pre-check.

    ``bucket_exists`` on a dead endpoint spends ~6s in urllib3 retries, which would make
    every cold start feel broken. A half-second connect attempt answers the same question.
    """
    host, _, port = endpoint.partition(":")
    try:
        with socket.create_connection((host, int(port or 9000)), timeout=timeout):
            return True
    except (OSError, ValueError):
        return False


def init_minio() -> bool:
    """Ensure the bucket exists. Returns whether MinIO is usable.

    Never raises: a missing object store must degrade to the local filesystem store, not
    stop the API from booting.
    """
    if not _reachable(settings.MINIO_ENDPOINT):
        log.warning("MinIO not listening at %s", settings.MINIO_ENDPOINT)
        storage.available = False
        return False

    try:
        client = get_storage_client()
        if not client.bucket_exists(settings.MINIO_BUCKET_NAME):
            client.make_bucket(settings.MINIO_BUCKET_NAME)
            log.info("Created bucket %s", settings.MINIO_BUCKET_NAME)
        else:
            log.info("Bucket %s already exists", settings.MINIO_BUCKET_NAME)
    except (S3Error, HTTPError, OSError, ValueError) as exc:
        log.warning("MinIO unavailable at %s: %s", settings.MINIO_ENDPOINT, exc)
        storage.available = False
        return False

    storage.available = True
    return True


def is_available() -> bool:
    return storage.available
