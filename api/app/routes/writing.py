"""Stateless writing assistance, separate from the story playback contract."""

import asyncio
from typing import Awaitable, TypeVar
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, Response
from pymongo.errors import PyMongoError
from urllib3.exceptions import HTTPError

from app.dependencies import RuntimeDep
from app.llm.base import LLMError
from app.models.writing import StoryboardRequest, StoryboardResponse, WritingRequest, WritingResponse
from app.runtime import Runtime
from app.assets.base import AssetStoreError
from app.models.writing_storage import (
    DocumentFileRequest,
    ImageUploadRequest,
    LibraryImageRequest,
    WorkspaceSave,
)
from app.services.writing_storage import WorkspaceConflict

router = APIRouter(prefix="/writing", tags=["writing"])

Proposal = TypeVar("Proposal")


@router.get("/status")
async def writing_status(runtime: Runtime = RuntimeDep) -> dict:
    return {"available": bool(runtime.writing.providers), "default_dialogue_count": 50,
            "default_panel_count": 8}


async def propose(work: Awaitable[Proposal], http_request: Request) -> Proposal:
    """Runs a proposal, and stops paying for one whose reader has gone away."""
    finished = asyncio.Event()

    async def disconnected():
        while not finished.is_set():
            if await http_request.is_disconnected():
                return
            await asyncio.sleep(0.2)

    generation = asyncio.create_task(work)
    disconnect = asyncio.create_task(disconnected())
    try:
        done, _ = await asyncio.wait({generation, disconnect}, return_when=asyncio.FIRST_COMPLETED)
        if generation in done:
            return await generation
        raise HTTPException(status_code=499, detail="Writing request cancelled")
    except LLMError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    finally:
        # Starlette probes disconnects inside an AnyIO cancellation scope. Mark the
        # loop finished as well, so a cancellation consumed by that probe cannot
        # keep response delivery waiting for a watcher that no longer has work.
        finished.set()
        generation.cancel()
        disconnect.cancel()
        await asyncio.gather(generation, disconnect, return_exceptions=True)


@router.post("/assist", response_model=WritingResponse)
async def assist(request: WritingRequest, http_request: Request, runtime: Runtime = RuntimeDep) -> WritingResponse:
    return await propose(runtime.writing.assist(request), http_request)


@router.post("/storyboard", response_model=StoryboardResponse)
async def storyboard(request: StoryboardRequest, http_request: Request,
                     runtime: Runtime = RuntimeDep) -> StoryboardResponse:
    return await propose(runtime.writing.storyboard(request), http_request)


async def storage_call(work):
    try:
        return await asyncio.wait_for(work, timeout=12)
    except WorkspaceConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Workspace not found") from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (TimeoutError, PyMongoError, AssetStoreError, OSError, HTTPError) as exc:
        raise HTTPException(status_code=503, detail="Storage is unavailable. Keep your draft open and retry saving.") from exc


@router.post("/workspaces/{workspace_id}")
async def open_workspace(workspace_id: UUID, runtime: Runtime = RuntimeDep) -> dict:
    return await storage_call(runtime.writing_storage.open(str(workspace_id)))


@router.put("/workspaces/{workspace_id}")
async def save_workspace(workspace_id: UUID, request: WorkspaceSave, runtime: Runtime = RuntimeDep) -> dict:
    return await storage_call(runtime.writing_storage.save(str(workspace_id), request))


@router.post("/workspaces/{workspace_id}/files")
async def create_file(workspace_id: UUID, request: DocumentFileRequest, runtime: Runtime = RuntimeDep) -> dict:
    return await storage_call(runtime.writing_storage.create_file(str(workspace_id), request))


@router.get("/workspaces/{workspace_id}/files/{file_id}")
async def read_file(workspace_id: UUID, file_id: str, runtime: Runtime = RuntimeDep) -> Response:
    found = await storage_call(runtime.writing_storage.read_file(str(workspace_id), file_id))
    if found is None:
        raise HTTPException(status_code=404, detail="Document file not found")
    data, content_type = found
    return Response(content=data, media_type=content_type,
                    headers={"Cache-Control": "private, no-store", "Content-Disposition": "attachment"})


@router.post("/workspaces/{workspace_id}/images")
async def create_image(workspace_id: UUID, request: ImageUploadRequest, runtime: Runtime = RuntimeDep) -> dict:
    return await storage_call(runtime.writing_storage.create_image(str(workspace_id), request))


@router.get("/library")
async def image_library(runtime: Runtime = RuntimeDep) -> dict:
    """Pictures an operator has put in the object store by hand -- see docs/IMAGES.md."""
    return await storage_call(runtime.writing_storage.library())


@router.post("/workspaces/{workspace_id}/images/library")
async def adopt_image(workspace_id: UUID, request: LibraryImageRequest, runtime: Runtime = RuntimeDep) -> dict:
    return await storage_call(runtime.writing_storage.adopt_image(str(workspace_id), request))


@router.get("/workspaces/{workspace_id}/images/{image_id}")
async def read_image(workspace_id: UUID, image_id: str, runtime: Runtime = RuntimeDep) -> Response:
    found = await storage_call(runtime.writing_storage.read_image(str(workspace_id), image_id))
    if found is None:
        raise HTTPException(status_code=404, detail="Picture not found")
    data, content_type = found
    # Inline, so a manuscript can show it; content-addressed, so it can be held forever;
    # never sniffed, so a mislabelled upload cannot become a script on this origin.
    return Response(content=data, media_type=content_type, headers={
        "Cache-Control": "private, max-age=31536000, immutable",
        "Content-Disposition": "inline",
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": "default-src 'none'; sandbox",
    })
