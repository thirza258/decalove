import asyncio
from base64 import b64encode
from types import SimpleNamespace
from uuid import uuid4

import pytest

from app.assets.base import AssetStoreError
from app.assets.png import encode_png
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


def picture(color=b"\xff\x00\x00") -> bytes:
    return encode_png(2, 2, [color * 2] * 2)


def test_illustrations_are_stored_once_served_inline_and_scoped_to_their_workspace(client):
    workspace_id, _ = workspace(client)
    other_id, _ = workspace(client)
    payload = {"content_type": "image/png", "data": b64encode(picture()).decode(), "alt": "  A red square  "}
    base = f"/api/v1/writing/workspaces/{workspace_id}/images"
    saved = client.post(base, json=payload)
    assert saved.status_code == 200
    image_id = saved.json()["id"]
    # A retried upload of identical bytes is the same object and the same identifier.
    assert client.post(base, json=payload).json()["id"] == image_id
    shown = client.get(f"{base}/{image_id}")
    assert shown.status_code == 200
    assert shown.content == picture()
    assert shown.headers["content-type"] == "image/png"
    assert shown.headers["content-disposition"] == "inline"
    assert shown.headers["x-content-type-options"] == "nosniff"
    assert client.get(f"/api/v1/writing/workspaces/{other_id}/images/{image_id}").status_code == 404
    # An illustration is not a manuscript download, and cannot be fetched as one.
    assert client.get(f"/api/v1/writing/workspaces/{workspace_id}/files/{image_id}").status_code == 404


@pytest.mark.parametrize("payload, expected", [
    ({"content_type": "image/png", "data": b64encode(b"<svg onload=alert(1)>").decode()}, "not a PNG"),
    ({"content_type": "image/svg+xml", "data": b64encode(b"<svg />").decode()}, None),
    ({"content_type": "image/png", "data": "not base64!"}, "could not be read"),
    ({"content_type": "image/png", "data": b64encode(b"\x89PNG\r\n\x1a\n" + b"0" * 5_000_001).decode()}, "up to 5 MB"),
])
def test_only_real_raster_pictures_within_the_size_limit_are_stored(client, payload, expected):
    workspace_id, _ = workspace(client)
    response = client.post(f"/api/v1/writing/workspaces/{workspace_id}/images", json=payload)
    assert response.status_code == 422
    if expected:
        assert expected in response.json()["detail"]
    assert not client.app.state.runtime.writing_storage.repository.files


def test_pictures_placed_in_the_store_by_hand_can_be_used_without_copying_them(client):
    workspace_id, _ = workspace(client)
    store = client.app.state.runtime.store
    asyncio.get_event_loop_policy().new_event_loop().run_until_complete(
        store.put("writing/library/rooftops.png", picture(b"\x00\x33\x66"), "image/png"))
    listed = client.get("/api/v1/writing/library").json()
    assert listed["prefix"] == "writing/library/"
    assert [p["name"] for p in listed["pictures"]] == ["rooftops.png"]
    base = f"/api/v1/writing/workspaces/{workspace_id}/images"
    adopted = client.post(f"{base}/library", json={"key": "writing/library/rooftops.png"})
    assert adopted.status_code == 200
    assert adopted.json()["alt"] == "rooftops"
    shown = client.get(f"{base}/{adopted.json()['id']}")
    assert shown.content == picture(b"\x00\x33\x66")
    assert shown.headers["content-type"] == "image/png"
    # The library is a fixed place in the object store, not an arbitrary path.
    assert client.post(f"{base}/library", json={"key": "writing/library/../../etc/passwd"}).status_code == 422
    assert client.post(f"{base}/library", json={"key": "characters/aiko.png"}).status_code == 422
    assert client.post(f"{base}/library", json={"key": "writing/library/missing.png"}).status_code == 422


def test_colour_notes_comments_and_a_storyboard_round_trip_and_reach_the_text_export(client):
    workspace_id, initial = workspace(client)
    data = initial["data"]
    document = data["library"]["documents"][0]
    document["title"] = "Rooftops"
    document["blocks"][0].update(text="The city went quiet.", marks=[
        {"kind": "highlight", "start": 4, "end": 8, "value": "amber"},
        {"kind": "color", "start": 4, "end": 8, "value": "plum"}])
    document["blocks"].append({**document["blocks"][0], "id": str(uuid4()), "kind": "image", "marks": [],
                               "text": "  Before the rain.  ", "speaker": "",
                               "image": {"id": "a" * 64, "alt": "  Wet rooftops at dusk  ", "width": 75}})
    document["notes"] = [{"id": str(uuid4()), "title": "Research", "body": "Rooftop access is locked after 8pm.",
                          "color": "teal", "updatedAt": "2026-09-21T10:00:00Z"}]
    document["comments"] = [{"id": str(uuid4()), "blockId": document["blocks"][0]["id"], "quote": "The city went quiet.",
                             "author": "Mara", "body": "Too calm — give her something to do.", "resolved": False,
                             "createdAt": "2026-09-21T10:01:00Z"}]
    document["storyboard"] = [{"id": str(uuid4()), "shot": "establishing", "title": "The roof",
                               "description": "Wet tiles, one open door.", "dialogue": "You came.",
                               "notes": "Hold before she turns.", "image": {"id": "b" * 64, "alt": "Rooftop", "width": 100}}]
    saved = client.put(f"/api/v1/writing/workspaces/{workspace_id}", json={"revision": 0, "data": data})
    assert saved.status_code == 200
    assert client.post(f"/api/v1/writing/workspaces/{workspace_id}").json()["data"] == data

    base = f"/api/v1/writing/workspaces/{workspace_id}/files"
    exported = client.post(base, json={"document": document, "format": "txt"}).json()
    # The client's exportText writes this same file -- see document.test.ts.
    assert client.get(f"{base}/{exported['id']}").text == (
        "Rooftops\n\nThe city went quiet.\n\n"
        "[Image: Wet rooftops at dusk]\n  Before the rain.  \n\n"
        "STORYBOARD\n1. ESTABLISHING — The roof\n   Wet tiles, one open door.\n"
        "   “You came.”\n   Note: Hold before she turns.\n   [Image: Rooftop]\n"
    )
    # A backup keeps the margin of the manuscript, not only its prose.
    backup = client.post(base, json={"document": document, "format": "json"}).json()
    assert client.get(f"{base}/{backup['id']}").json()["document"] == document


@pytest.mark.parametrize("patch", [
    {"marks": [{"kind": "color", "start": 0, "end": 3}]},
    {"marks": [{"kind": "bold", "start": 0, "end": 3, "value": "plum"}]},
    {"marks": [{"kind": "color", "start": 0, "end": 3, "value": "chartreuse"}]},
    {"kind": "image"},
    {"image": {"id": "a" * 64, "alt": "", "width": 100}},
    {"kind": "image", "image": {"id": "not-a-digest", "alt": "", "width": 100}},
    {"kind": "image", "image": {"id": "a" * 64, "alt": "", "width": 5}},
])
def test_storage_schema_rejects_impossible_colours_and_pictures(client, patch):
    workspace_id, initial = workspace(client)
    initial["data"]["library"]["documents"][0]["blocks"][0].update(text="Rain.", **patch)
    assert client.put(f"/api/v1/writing/workspaces/{workspace_id}",
                      json={"revision": 0, "data": initial["data"]}).status_code == 422
