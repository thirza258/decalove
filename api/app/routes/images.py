from typing import Optional
from fastapi import APIRouter, UploadFile, File, Form, status
from fastapi.responses import Response
from app.models.image import ImageOut
from app.services import image_service

router = APIRouter(prefix="/images", tags=["images"])


@router.post("/upload", response_model=ImageOut, status_code=status.HTTP_201_CREATED)
async def upload_image(
    file: UploadFile = File(...),
    image_type: str = Form(...),
    scene_id: Optional[str] = Form(None),
):
    """Upload an image to MinIO storage.

    - **file**: The image file to upload
    - **image_type**: One of 'background', 'character', 'item'
    - **scene_id**: Optional scene ID to associate the image with
    """
    return await image_service.upload_image(file, image_type, scene_id)


@router.get("/{image_id}", response_model=ImageOut)
async def get_image_metadata(image_id: str):
    """Get image metadata including a fresh presigned URL."""
    return await image_service.get_image_metadata(image_id)


@router.get("/{image_id}/view")
async def view_image(image_id: str):
    """Proxy the actual image data from MinIO.

    Returns the raw image bytes with the correct content type,
    so this endpoint can be used directly as an `<img>` src.
    """
    data, content_type = await image_service.get_image_data(image_id)
    return Response(content=data, media_type=content_type)
