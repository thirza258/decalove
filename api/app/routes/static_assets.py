import asyncio
import mimetypes
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from minio.error import S3Error

from app.config import settings
from app.storage import get_storage_client, is_available

router = APIRouter(tags=["static"])

LOCAL_GAME_IMAGES_DIR = Path(__file__).resolve().parent.parent.parent.parent / 'game' / 'images'

def _fetch_from_minio(object_name: str) -> bytes | None:
    if not is_available():
        return None
    try:
        client = get_storage_client()
        response = client.get_object(settings.MINIO_BUCKET_NAME, object_name)
        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()
    except S3Error as e:
        if e.code == "NoSuchKey":
            return None
        # Could log here, but returning None falls back to local
        return None
    except Exception:
        return None

def _fetch_from_local(path: str) -> bytes | None:
    local_path = LOCAL_GAME_IMAGES_DIR / path
    try:
        resolved = local_path.resolve()
        # Prevent directory traversal
        if not str(resolved).startswith(str(LOCAL_GAME_IMAGES_DIR.resolve())):
            return None
        
        if resolved.is_file():
            return resolved.read_bytes()
    except Exception:
        pass
    return None

@router.get("/static/images/{path:path}")
async def get_static_image(path: str):
    object_name = f"static/images/{path}"
    
    content = await asyncio.to_thread(_fetch_from_minio, object_name)
    
    if content is None:
        content = await asyncio.to_thread(_fetch_from_local, path)
        
    if content is None:
        raise HTTPException(status_code=404, detail="Image not found")
        
    content_type, _ = mimetypes.guess_type(path)
    if not content_type:
        content_type = "application/octet-stream"
        
    headers = {
        "Cache-Control": "public, max-age=31536000, immutable"
    }
    
    return Response(content=content, media_type=content_type, headers=headers)
