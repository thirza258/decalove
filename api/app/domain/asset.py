"""Generated image bookkeeping — PRD §18/§19."""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field


class AssetRecord(BaseModel):
    """One stored image, addressed by a content-derived cache key.

    ``cache_key`` is what makes PRD §19 work: the same character/expression/pose/location/
    time/weather/composition always resolves to the same key, so the second scene on the
    rooftop at sunset costs nothing.
    """

    model_config = ConfigDict(extra="ignore")

    id: str
    cache_key: str
    kind: str = "background"
    world_id: str = ""
    object_key: str = ""
    content_type: str = "image/png"
    size_bytes: int = 0
    prompt: str = ""
    provider: str = ""
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
