from bson import ObjectId
from datetime import datetime, timezone
from fastapi import HTTPException
from app.database import get_db
from app.models.scene import SceneCreate, SceneUpdate


async def create_scene(scene: SceneCreate) -> dict:
    db = get_db()
    now = datetime.now(timezone.utc)
    scene_doc = {
        **scene.model_dump(),
        "created_at": now,
        "updated_at": now,
    }
    result = await db.scenes.insert_one(scene_doc)
    created_scene = await db.scenes.find_one({"_id": result.inserted_id})
    return created_scene


async def get_scenes() -> list:
    db = get_db()
    scenes = await db.scenes.find().to_list(1000)
    return scenes


async def get_scene_by_id(scene_id: str) -> dict:
    db = get_db()
    try:
        obj_id = ObjectId(scene_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid scene ID format")

    scene = await db.scenes.find_one({"_id": obj_id})
    if scene is None:
        raise HTTPException(status_code=404, detail="Scene not found")
    return scene


async def update_scene(scene_id: str, scene_update: SceneUpdate) -> dict:
    db = get_db()
    try:
        obj_id = ObjectId(scene_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid scene ID format")

    update_data = {k: v for k, v in scene_update.model_dump().items() if v is not None}
    if update_data:
        update_data["updated_at"] = datetime.now(timezone.utc)
        result = await db.scenes.update_one(
            {"_id": obj_id}, {"$set": update_data}
        )
        if result.modified_count == 0 and result.matched_count == 0:
            raise HTTPException(status_code=404, detail="Scene not found")

    updated_scene = await db.scenes.find_one({"_id": obj_id})
    return updated_scene


async def delete_scene(scene_id: str) -> bool:
    db = get_db()
    try:
        obj_id = ObjectId(scene_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid scene ID format")

    result = await db.scenes.delete_one({"_id": obj_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Scene not found")
    return True
