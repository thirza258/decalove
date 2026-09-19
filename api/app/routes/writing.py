"""Stateless writing assistance, separate from the story playback contract."""

import asyncio
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, Response
from pymongo.errors import PyMongoError
from urllib3.exceptions import HTTPError

from app.dependencies import RuntimeDep
from app.llm.base import LLMError
from app.models.writing import WritingRequest, WritingResponse
from app.runtime import Runtime
from app.assets.base import AssetStoreError
from app.models.writing_storage import DocumentFileRequest, WorkspaceSave
from app.services.writing_storage import WorkspaceConflict

router = APIRouter(prefix="/writing", tags=["writing"])


@router.get("/status")
async def writing_status(runtime: Runtime = RuntimeDep) -> dict:
    return {"available": bool(runtime.writing.providers), "default_dialogue_count": 50}


@router.post("/assist", response_model=WritingResponse)
async def assist(request: WritingRequest, http_request: Request, runtime: Runtime = RuntimeDep) -> WritingResponse:
    finished = asyncio.Event()

    async def disconnected():
        while not finished.is_set():
            if await http_request.is_disconnected():
                return
            await asyncio.sleep(0.2)

    generation = asyncio.create_task(runtime.writing.assist(request))
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


async def storage_call(work):
    try:
        return await asyncio.wait_for(work, timeout=12)
    except WorkspaceConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Workspace not found") from exc
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
