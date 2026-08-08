from typing import Optional, List, Annotated, Any
from datetime import datetime, timezone
from pydantic import BaseModel, Field, BeforeValidator


def validate_object_id(v: Any) -> str:
    """Convert ObjectId to string or validate string format."""
    from bson import ObjectId
    if isinstance(v, ObjectId):
        return str(v)
    if isinstance(v, str) and ObjectId.is_valid(v):
        return v
    raise ValueError(f"Invalid ObjectId: {v}")


PyObjectId = Annotated[str, BeforeValidator(validate_object_id)]


class ChoiceModel(BaseModel):
    text: str
    next_scene_id: str


class DialogueEntryModel(BaseModel):
    character: str
    text: str
    emotion: Optional[str] = "neutral"


class SceneBase(BaseModel):
    title: str
    dialogue: List[DialogueEntryModel] = []
    background_image_url: str
    character_image_url: Optional[str] = None
    choices: Optional[List[ChoiceModel]] = []


class SceneCreate(SceneBase):
    pass


class SceneUpdate(BaseModel):
    title: Optional[str] = None
    dialogue: Optional[List[DialogueEntryModel]] = None
    background_image_url: Optional[str] = None
    character_image_url: Optional[str] = None
    choices: Optional[List[ChoiceModel]] = None


class SceneOut(BaseModel):
    id: PyObjectId = Field(alias="_id")
    title: str
    dialogue: List[DialogueEntryModel] = []
    background_image_url: str
    character_image_url: Optional[str] = None
    choices: Optional[List[ChoiceModel]] = []
    created_at: datetime
    updated_at: datetime

    model_config = {
        "populate_by_name": True,
        "json_encoders": {datetime: lambda v: v.isoformat()},
    }


class SceneFullOut(SceneOut):
    """Scene with fully resolved presigned URLs for the game client."""
    background_image_full_url: str = ""
    character_image_full_url: Optional[str] = None
