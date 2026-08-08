from typing import List
from fastapi import APIRouter, status, Depends
from app.models.scene import SceneCreate, SceneUpdate, SceneOut, SceneFullOut
from app.services import scene_service
from app.services import image_service

router = APIRouter(prefix="/scenes", tags=["scenes"])

@router.post("", response_model=SceneOut, status_code=status.HTTP_201_CREATED)
async def create_scene(scene: SceneCreate):
    return await scene_service.create_scene(scene)

@router.get("", response_model=List[SceneOut])
async def list_scenes():
    return await scene_service.get_scenes()

@router.get("/{scene_id}", response_model=SceneOut)
async def get_scene(scene_id: str):
    return await scene_service.get_scene_by_id(scene_id)

@router.put("/{scene_id}", response_model=SceneOut)
async def update_scene(scene_id: str, scene_update: SceneUpdate):
    return await scene_service.update_scene(scene_id, scene_update)

@router.delete("/{scene_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_scene(scene_id: str):
    await scene_service.delete_scene(scene_id)

@router.get("/{scene_id}/full", response_model=SceneFullOut)
async def get_scene_full(scene_id: str):
    scene = await scene_service.get_scene_by_id(scene_id)
    
    # Resolve images
    # If the URL stored is just an object key or if we need a fresh presigned URL
    # Assuming background_image_url stores the object key for flexibility
    # Wait, the requirements state background_image_url points to MinIO. 
    # For simplicity, if it's an object key, we generate a presigned URL here.
    # Otherwise if it's already a URL, we just pass it.
    bg_url = scene.get("background_image_url", "")
    if bg_url and not bg_url.startswith("http"):
        bg_url = image_service.get_presigned_url(bg_url)
        
    char_url = scene.get("character_image_url", "")
    if char_url and not char_url.startswith("http"):
        char_url = image_service.get_presigned_url(char_url)
        
    scene["background_image_full_url"] = bg_url if bg_url else scene.get("background_image_url")
    scene["character_image_full_url"] = char_url if char_url else scene.get("character_image_url")
    
    return scene
