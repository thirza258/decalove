"""MongoDB connection.

``try_connect`` actually *pings* the server rather than assuming a client object means a
live database -- Motor connects lazily, so without the ping a dead Mongo only surfaces on
the first query, halfway through a player's turn.
"""

from __future__ import annotations

import logging

from motor.motor_asyncio import AsyncIOMotorClient
from pymongo.errors import PyMongoError

from app.config import settings

log = logging.getLogger(__name__)


class Database:
    client: AsyncIOMotorClient | None = None
    db = None
    available: bool = False


db = Database()


async def try_connect(timeout_ms: int | None = None) -> bool:
    """Connect and ping. Returns whether MongoDB is usable."""
    timeout = timeout_ms if timeout_ms is not None else settings.STORAGE_PROBE_TIMEOUT_MS
    try:
        client: AsyncIOMotorClient = AsyncIOMotorClient(
            settings.MONGODB_URL,
            serverSelectionTimeoutMS=timeout,
            connectTimeoutMS=timeout,
        )
        await client.admin.command("ping")
    except (PyMongoError, OSError) as exc:
        log.warning("MongoDB unavailable at %s: %s", settings.MONGODB_URL, exc)
        db.available = False
        return False

    db.client = client
    db.db = client[settings.MONGODB_DB_NAME]
    db.available = True
    log.info("Connected to MongoDB database %s", settings.MONGODB_DB_NAME)
    return True


async def connect_to_mongo() -> bool:
    return await try_connect()


async def close_mongo_connection() -> None:
    if db.client is not None:
        db.client.close()
        db.client = None
        db.db = None
        db.available = False
        log.info("Closed MongoDB connection")


def get_db():
    return db.db


def is_available() -> bool:
    return db.available
