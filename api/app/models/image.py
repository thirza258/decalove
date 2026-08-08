from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field
from app.models.scene import PyObjectId


class ImageOut(BaseModel):
    id: PyObjectId = Field(alias="_id")
    filename: str
    bucket: str
    object_key: str
    content_type: str
    size_bytes: int
    url: str
    scene_id: Optional[str] = None
    image_type: str  # 'background', 'character', 'item'
    created_at: datetime

    model_config = {
        "populate_by_name": True,
        "json_encoders": {datetime: lambda v: v.isoformat()},
    }
