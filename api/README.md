# Decalove API — Visual Novel Game Backend

FastAPI backend for an AI-agent-driven visual novel game, with MongoDB for data and MinIO (S3-compatible) for image storage.

## Architecture

```
┌──────────────┐       ┌──────────────┐       ┌──────────────┐
│   Game Client │◄─────►│   FastAPI    │◄─────►│   MongoDB    │
│  (Frontend)   │       │  (Backend)   │       │   (Data)     │
└──────────────┘       └──────┬───────┘       └──────────────┘
                              │
                       ┌──────▼───────┐
                       │    MinIO      │
                       │  (Images)     │
                       └──────────────┘
```

## Quick Start

### 1. Start infrastructure services

```bash
docker compose up -d
```

This starts:
- **MongoDB 7** on port `27017`
- **MinIO** on port `9000` (API) and `9001` (Console UI)

### 2. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 3. Run the API server

```bash
uvicorn app.main:app --reload --port 8000
```

### 4. Open in browser

- **API docs (Swagger)**: http://localhost:8000/docs
- **MinIO Console**: http://localhost:9001 (login: `minioadmin` / `minioadmin`)
- **Health check**: http://localhost:8000/health

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/health` | Health check |
| `POST` | `/api/v1/seed` | Seed database with sample scene |
| `POST` | `/api/v1/scenes` | Create a new scene |
| `GET` | `/api/v1/scenes` | List all scenes |
| `GET` | `/api/v1/scenes/{id}` | Get a specific scene |
| `PUT` | `/api/v1/scenes/{id}` | Update a scene |
| `DELETE` | `/api/v1/scenes/{id}` | Delete a scene |
| `GET` | `/api/v1/scenes/{id}/full` | Get scene with resolved image URLs |
| `POST` | `/api/v1/images/upload` | Upload an image to MinIO |
| `GET` | `/api/v1/images/{id}` | Get image metadata |
| `GET` | `/api/v1/images/{id}/view` | View/proxy the actual image |

## Environment Variables

See [`.env`](.env) for all configurable settings. Key variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `MONGODB_URL` | `mongodb://root:rootpassword@localhost:27017` | MongoDB connection string |
| `MINIO_ENDPOINT` | `localhost:9000` | MinIO server endpoint |
| `MINIO_BUCKET_NAME` | `decalove-assets` | S3 bucket for game assets |

## Data Models

### Scene
Represents a visual novel scene with dialogue, background/character images, and player choices.

### GeneratedImage
Tracks images stored in MinIO with metadata (type, size, presigned URL).
