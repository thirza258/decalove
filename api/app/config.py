from typing import List
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Application
    PROJECT_NAME: str = "Decalove AI Backend"
    API_PREFIX: str = "/api/v1"
    CORS_ORIGINS: List[str] = ["*"]

    # MongoDB
    MONGODB_URL: str = "mongodb://root:rootpassword@localhost:27017"
    MONGODB_DB_NAME: str = "decalove_db"

    # MinIO
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_SECURE: bool = False
    MINIO_BUCKET_NAME: str = "decalove-assets"

    model_config = {
        "env_file": ".env",
        "case_sensitive": True,
    }


settings = Settings()
