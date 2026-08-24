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
from app.routes import assets, games, images, scenes
from app.runtime import Runtime, build_runtime
from app.services.scene_service import create_scene

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
)
log = logging.getLogger("decalove")


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
# Legacy authored-scene CRUD: predates the story engine, still MongoDB-only.
app.include_router(scenes.router, prefix=settings.API_PREFIX, dependencies=[Depends(require_mongo)])
app.include_router(images.router, prefix=settings.API_PREFIX, dependencies=[Depends(require_mongo)])


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
