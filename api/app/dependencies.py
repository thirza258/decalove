"""FastAPI dependencies."""

from __future__ import annotations

from fastapi import Depends, HTTPException, Request, status

from app.database import is_available as mongo_available
from app.runtime import Runtime


def get_runtime(request: Request) -> Runtime:
    runtime: Runtime | None = getattr(request.app.state, "runtime", None)
    if runtime is None:  # pragma: no cover - only reachable if startup failed
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="runtime not initialised"
        )
    return runtime


def require_mongo() -> None:
    """Guard for the legacy scene/image CRUD, which talks to MongoDB directly.

    The game engine runs without MongoDB; these older endpoints do not, and a clear 503
    beats an AttributeError from a ``None`` database handle.
    """
    if not mongo_available():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="MongoDB is unavailable; start it with `docker compose up -d`.",
        )


RuntimeDep = Depends(get_runtime)
