"""Real MongoDB + MinIO persistence; each test owns its database and bucket."""

import json
from uuid import uuid4

import pytest
from motor.motor_asyncio import AsyncIOMotorClient

from conftest import needs_minio, needs_mongo
from app.assets.minio_store import MinioAssetStore
from app.config import settings
from app.models.writing_storage import DocumentFileRequest, WorkspaceData, WorkspaceSave
from app.repositories.writing_repo import MongoWritingRepository
from app.services.writing_storage import WritingStorage, WorkspaceConflict
from app.storage import get_storage_client

pytestmark = [needs_mongo, needs_minio, pytest.mark.integration]


async def test_workspace_and_files_survive_new_service_instances():
    suffix = uuid4().hex[:12]
    mongo = AsyncIOMotorClient(settings.MONGODB_URL, serverSelectionTimeoutMS=3000)
    database_name = f"decalove_writing_test_{suffix}"
    bucket = f"decalove-writing-test-{suffix}"
    minio = get_storage_client()
    minio.make_bucket(bucket)
    try:
        service = WritingStorage(MongoWritingRepository(mongo[database_name]), MinioAssetStore(bucket), backend="mongo")
        workspace_id = str(uuid4())
        original = await service.open(workspace_id)
        data = WorkspaceData.model_validate(original["data"])
        doc = data.library.documents[0]
        doc.title = "Persisted manuscript"
        doc.blocks[0].text = "The letter remained unopened."
        data.progress.completed = ["story-want"]
        await service.save(workspace_id, WorkspaceSave(revision=0, data=data))
        backup = await service.create_file(workspace_id, DocumentFileRequest(document=doc, format="json"))
        fresh = WritingStorage(MongoWritingRepository(mongo[database_name]), MinioAssetStore(bucket), backend="mongo")
        reloaded = await fresh.open(workspace_id)
        assert reloaded["revision"] == 1
        assert reloaded["data"]["library"]["documents"][0]["title"] == doc.title
        assert reloaded["data"]["progress"]["completed"] == ["story-want"]
        body, content_type = await fresh.read_file(workspace_id, backup["id"])
        assert content_type == "application/json"
        assert json.loads(body)["document"]["blocks"][0]["text"] == doc.blocks[0].text
        doc.title = "Stale overwrite"
        with pytest.raises(WorkspaceConflict):
            await fresh.save(workspace_id, WorkspaceSave(revision=0, data=data))
        assert await fresh.read_file(str(uuid4()), backup["id"]) is None
    finally:
        await mongo.drop_database(database_name)
        mongo.close()
        for item in minio.list_objects(bucket, recursive=True):
            minio.remove_object(bucket, item.object_name)
        minio.remove_bucket(bucket)
