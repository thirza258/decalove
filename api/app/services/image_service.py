import io
import uuid
import datetime
from fastapi import HTTPException, UploadFile
from bson import ObjectId
from app.config import settings
from app.storage import get_storage_client
from app.database import get_db


async def upload_image(file: UploadFile, image_type: str, scene_id: str = None) -> dict:
    """Upload an image to MinIO and save metadata in MongoDB."""
    client = get_storage_client()
    db = get_db()

    file_extension = file.filename.split(".")[-1] if "." in file.filename else "png"
    unique_filename = f"{uuid.uuid4()}.{file_extension}"
    object_key = f"{image_type}s/{unique_filename}"

    # Read file content
    file_content = await file.read()
    size_bytes = len(file_content)

    # Upload to MinIO
    client.put_object(
        bucket_name=settings.MINIO_BUCKET_NAME,
        object_name=object_key,
        data=io.BytesIO(file_content),
        length=size_bytes,
        content_type=file.content_type or "image/png",
    )

    # Generate presigned URL (valid for 7 days)
    url = client.presigned_get_object(
        settings.MINIO_BUCKET_NAME,
        object_key,
        expires=datetime.timedelta(days=7),
    )

    # Save metadata to MongoDB
    now = datetime.datetime.now(datetime.timezone.utc)
    image_doc = {
        "filename": file.filename,
        "bucket": settings.MINIO_BUCKET_NAME,
        "object_key": object_key,
        "content_type": file.content_type or "image/png",
        "size_bytes": size_bytes,
        "url": url,
        "scene_id": scene_id,
        "image_type": image_type,
        "created_at": now,
    }

    result = await db.images.insert_one(image_doc)
    created_image = await db.images.find_one({"_id": result.inserted_id})

    return created_image


async def get_image_metadata(image_id: str) -> dict:
    """Get image metadata from MongoDB, refreshing the presigned URL."""
    db = get_db()
    try:
        obj_id = ObjectId(image_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid image ID format")

    image = await db.images.find_one({"_id": obj_id})
    if image is None:
        raise HTTPException(status_code=404, detail="Image not found")

    # Refresh presigned URL
    client = get_storage_client()
    url = client.presigned_get_object(
        settings.MINIO_BUCKET_NAME,
        image["object_key"],
        expires=datetime.timedelta(days=7),
    )

    # Update stored URL
    await db.images.update_one(
        {"_id": obj_id}, {"$set": {"url": url}}
    )
    image["url"] = url

    return image


def get_presigned_url(object_key: str) -> str:
    """Generate a fresh presigned URL for an object key."""
    client = get_storage_client()
    try:
        url = client.presigned_get_object(
            settings.MINIO_BUCKET_NAME,
            object_key,
            expires=datetime.timedelta(days=7),
        )
        return url
    except Exception as e:
        print(f"Error generating presigned url: {e}")
        return ""


async def get_image_data(image_id: str) -> tuple[bytes, str]:
    """Fetch actual image bytes from MinIO for proxying."""
    db = get_db()
    try:
        obj_id = ObjectId(image_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid image ID format")

    image = await db.images.find_one({"_id": obj_id})
    if image is None:
        raise HTTPException(status_code=404, detail="Image not found")

    client = get_storage_client()
    try:
        response = client.get_object(
            settings.MINIO_BUCKET_NAME,
            image["object_key"],
        )
        data = response.read()
        response.close()
        response.release_conn()
        return data, image["content_type"]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to retrieve image: {e}")
