from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.config import settings
from app.database import connect_to_mongo, close_mongo_connection, get_db
from app.storage import init_minio
from app.routes import scenes, images
from app.models.scene import SceneCreate
from app.services.scene_service import create_scene

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await connect_to_mongo()
    init_minio()
    yield
    # Shutdown
    await close_mongo_connection()

app = FastAPI(
    title=settings.PROJECT_NAME,
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes
app.include_router(scenes.router, prefix=settings.API_PREFIX)
app.include_router(images.router, prefix=settings.API_PREFIX)

@app.get("/health")
async def health_check():
    return {"status": "healthy"}

@app.post(f"{settings.API_PREFIX}/seed")
async def seed_data():
    scene = SceneCreate(
        title="First Encounter",
        dialogue=[
            {"character": "Hero", "text": "Who are you?", "emotion": "confused"},
            {"character": "Stranger", "text": "I'm just a traveler.", "emotion": "neutral"}
        ],
        background_image_url="backgrounds/forest.jpg",
        choices=[
            {"text": "Attack", "next_scene_id": "000000000000000000000001"},
            {"text": "Talk", "next_scene_id": "000000000000000000000002"}
        ]
    )
    created_scene = await create_scene(scene)
    return {"message": "Database seeded with initial scene", "scene": created_scene}
