from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.assets.base import AssetStoreError
from app.models.writing_storage import DocumentFileRequest, WorkspaceData, WorkspaceSave
from app.repositories.writing_repo import InMemoryWritingRepository
from app.services.writing_storage import WritingStorage, WorkspaceConflict


def workspace(client):
    workspace_id = str(uuid4())
    response = client.post(f"/api/v1/writing/workspaces/{workspace_id}")
    assert response.status_code == 200
    return workspace_id, response.json()


def test_workspace_round_trip_restores_formatted_drafts_notes_and_course_progress(client):
    workspace_id, original = workspace(client)
    data = original["data"]
    document = data["library"]["documents"][0]
    document.update(title="A quiet reunion", prompt="  Keep the pause.\n", reference="Only Mara knows.")
    document["blocks"][0].update(text="🙂 A remembered promise.", marks=[{"kind": "bold", "start": 3, "end": 15}], alignment="center", font="sans", size=20)
    data["progress"] = {"completed": ["narration-pov"], "exercises": {"narration-pov": "  My close perspective.  "}}
    saved = client.put(f"/api/v1/writing/workspaces/{workspace_id}", json={"revision": 0, "data": data})
    assert saved.status_code == 200
    assert saved.json()["revision"] == 1
    loaded = client.post(f"/api/v1/writing/workspaces/{workspace_id}").json()
    assert loaded["data"] == data
    assert loaded["storage"] == "memory"
    assert loaded["files"] == "local"


def test_stale_saves_conflict_but_retry_of_lost_response_is_idempotent(client):
    workspace_id, initial = workspace(client)
    path = f"/api/v1/writing/workspaces/{workspace_id}"
    request = {"revision": 0, "data": initial["data"]}
    request["data"]["library"]["documents"][0]["title"] = "First tab"
    assert client.put(path, json=request).json()["revision"] == 1
    assert client.put(path, json=request).json()["revision"] == 1
    request["data"]["library"]["documents"][0]["title"] = "Stale second tab"
    assert client.put(path, json=request).status_code == 409
    assert client.post(path).json()["data"]["library"]["documents"][0]["title"] == "First tab"


def test_backups_and_exports_use_existing_asset_store_and_workspace_scoping(client):
    workspace_id, initial = workspace(client)
    other_id, _ = workspace(client)
    document = initial["data"]["library"]["documents"][0]
    document["title"] = "Rain & promises"
    document["blocks"][0].update(kind="dialogue", text="  I kept it.  ", speaker="Mara")
    base = f"/api/v1/writing/workspaces/{workspace_id}/files"
    request = {"document": document, "format": "json"}
    backup = client.post(base, json=request)
    assert backup.status_code == 200
    file_id = backup.json()["id"]
    assert client.post(base, json=request).json()["id"] == file_id
    downloaded = client.get(f"{base}/{file_id}")
    assert downloaded.status_code == 200
    assert downloaded.headers["cache-control"] == "private, no-store"
    assert downloaded.json() == {"version": 1, "document": document}
    assert client.get(f"/api/v1/writing/workspaces/{other_id}/files/{file_id}").status_code == 404
    plain = client.post(base, json={**request, "format": "txt"}).json()
    assert "Mara:   I kept it.  " in client.get(f"{base}/{plain['id']}").text
    assert client.app.state.runtime.writing_storage.store is client.app.state.runtime.store


def test_storage_schema_rejects_invalid_formatting_and_duplicate_documents(client):
    workspace_id, initial = workspace(client)
    doc = initial["data"]["library"]["documents"][0]
    doc["blocks"][0]["marks"] = [{"kind": "bold", "start": 0, "end": 10}]
    path = f"/api/v1/writing/workspaces/{workspace_id}"
    assert client.put(path, json={"revision": 0, "data": initial["data"]}).status_code == 422
    doc["blocks"][0]["marks"] = []
    initial["data"]["library"]["documents"].append(doc)
    assert client.put(path, json={"revision": 0, "data": initial["data"]}).status_code == 422


async def test_file_metadata_is_not_published_after_object_store_failure():
    class Unavailable:
        name = "minio"

        async def put(self, *args):
            raise AssetStoreError("offline")

    repo = InMemoryWritingRepository()
    service = WritingStorage(repo, Unavailable(), backend="memory")
    workspace_id = str(uuid4())
    await service.open(workspace_id)
    with pytest.raises(AssetStoreError):
        await service.create_file(workspace_id, DocumentFileRequest(document=WorkspaceData().library.documents[0], format="json"))
    assert not repo.files


async def test_separate_readers_cannot_overwrite_a_newer_revision():
    repo = InMemoryWritingRepository()
    service = WritingStorage(repo, SimpleNamespace(name="local"), backend="memory")
    workspace_id = str(uuid4())
    data = WorkspaceData()
    await repo.ensure(workspace_id, data.model_dump(mode="json"))
    data.library.documents[0].title = "First writer"
    await service.save(workspace_id, WorkspaceSave(revision=0, data=data))
    data.library.documents[0].title = "Second writer"
    with pytest.raises(WorkspaceConflict):
        await service.save(workspace_id, WorkspaceSave(revision=0, data=data))
