from minio import Minio
from app.config import settings

class Storage:
    client: Minio = None

storage = Storage()

def get_storage_client():
    if storage.client is None:
        storage.client = Minio(
            settings.MINIO_ENDPOINT,
            access_key=settings.MINIO_ACCESS_KEY,
            secret_key=settings.MINIO_SECRET_KEY,
            secure=settings.MINIO_SECURE
        )
    return storage.client

def init_minio():
    client = get_storage_client()
    found = client.bucket_exists(settings.MINIO_BUCKET_NAME)
    if not found:
        client.make_bucket(settings.MINIO_BUCKET_NAME)
        # Set bucket policy for public read access if needed
        # policy = '{"Version":"2012-10-17","Statement":[{"Action":["s3:GetObject"],"Effect":"Allow","Principal":{"AWS":["*"]},"Resource":["arn:aws:s3:::%s/*"]}]}' % settings.MINIO_BUCKET_NAME
        # client.set_bucket_policy(settings.MINIO_BUCKET_NAME, policy)
        print(f"Created bucket {settings.MINIO_BUCKET_NAME}")
    else:
        print(f"Bucket {settings.MINIO_BUCKET_NAME} already exists")
