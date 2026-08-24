"""Generated asset delivery — PRD §22 ``GET /api/assets/{asset_id}``."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, status
from fastapi.responses import Response

from app.dependencies import RuntimeDep
from app.domain.asset import AssetRecord
from app.runtime import Runtime

router = APIRouter(prefix="/assets", tags=["assets"])


@router.get("/{asset_id}", response_model=AssetRecord)
async def get_asset(asset_id: str, runtime: Runtime = RuntimeDep) -> AssetRecord:
    record = await runtime.asset_service.metadata(asset_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="asset not found")
    return record


@router.get("/{asset_id}/view")
async def view_asset(asset_id: str, runtime: Runtime = RuntimeDep) -> Response:
    """Raw bytes, so the URL can be handed straight to ``renpy.fetch``."""
    found = await runtime.asset_service.read(asset_id)
    if found is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="asset not found")
    data, content_type = found
    return Response(
        content=data,
        media_type=content_type,
        headers={"Cache-Control": "public, max-age=31536000, immutable"},
    )
