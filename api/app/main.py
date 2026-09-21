"""Decalove API entrypoint."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.database import is_available as mongo_available
from app.dependencies import RuntimeDep, require_mongo
from app.models.scene import SceneCreate, SceneOut
from app.routes import assets, games, images, scenes, static_assets, writing
from app.runtime import Runtime, build_runtime
from app.services.scene_service import create_scene

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
)
log = logging.getLogger("decalove")


class _ProbeFilter(logging.Filter):
    """Drops the container healthcheck's own requests from the access log.

    The probe runs every 30s forever and always says the same thing, so left in it is
    most of the log by volume and pushes real traffic out of whatever window an
    operator is actually reading. A failing probe is still visible -- Docker reports
    the container unhealthy -- so nothing is lost by not narrating the passing ones.

    Only 2xx/3xx are dropped: a /health that starts answering 500 is a real event.
    """

    _QUIET = ("/health",)

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if not isinstance(args, tuple) or len(args) < 5:
            return True
        # uvicorn.access formats as: '%s - "%s %s HTTP/%s" %d' %
        # (client_addr, method, full_path, http_version, status_code)
        path, status = args[2], args[4]
        return not (
            isinstance(path, str)
            and path in self._QUIET
            and isinstance(status, int)
            and status < 400
        )


logging.getLogger("uvicorn.access").addFilter(_ProbeFilter())


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.runtime = await build_runtime(settings)
    # Started here rather than in build_runtime so that constructing a runtime (in tests,
    # or for a one-shot script) never leaves a background loop running.
    app.state.runtime.maintenance.start()
    try:
        yield
    finally:
        await app.state.runtime.close()


app = FastAPI(
    title=settings.PROJECT_NAME,
    description=(
        "AI-directed visual novel backend. The LLM writes the story; this service owns "
        "the state."
    ),
    lifespan=lifespan,
)

# A wildcard origin and credentials are mutually exclusive in every browser -- sending
# both makes the response fail CORS outright, which would break the Ren'Py web build.
_wildcard = "*" in settings.CORS_ORIGINS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=not _wildcard,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(games.router, prefix=settings.API_PREFIX)
app.include_router(assets.router, prefix=settings.API_PREFIX)
app.include_router(writing.router, prefix=settings.API_PREFIX)
# Legacy authored-scene CRUD: predates the story engine, still MongoDB-only.
app.include_router(scenes.router, prefix=settings.API_PREFIX, dependencies=[Depends(require_mongo)])
app.include_router(images.router, prefix=settings.API_PREFIX, dependencies=[Depends(require_mongo)])
app.include_router(static_assets.router, prefix=settings.API_PREFIX)


@app.get("/health", tags=["ops"])
async def health_check(runtime: Runtime = RuntimeDep) -> dict:
    """Says which backend each seam actually resolved to, not just 'healthy'."""
    detail = runtime.describe()
    return {
        "status": "healthy",
        "mongodb": mongo_available(),
        **detail,
    }


@app.post(f"{settings.API_PREFIX}/seed", tags=["ops"], dependencies=[Depends(require_mongo)])
async def seed_data():
    scene = SceneCreate(
        title="First Encounter",
        dialogue=[
            {"character": "Hero", "text": "Who are you?", "emotion": "confused"},
            {"character": "Stranger", "text": "I'm just a traveler.", "emotion": "neutral"},
        ],
        background_image_url="backgrounds/forest.jpg",
        choices=[
            {"text": "Attack", "next_scene_id": "000000000000000000000001"},
            {"text": "Talk", "next_scene_id": "000000000000000000000002"},
        ],
    )
    created_scene = await create_scene(scene)
    # Validate on the way out: the raw document carries a BSON ObjectId, which the
    # JSON encoder cannot serialise. SceneOut's PyObjectId converts it to a string.
    return {
        "message": "Database seeded with initial scene",
        "scene": SceneOut.model_validate(created_scene).model_dump(by_alias=True, mode="json"),
    }
