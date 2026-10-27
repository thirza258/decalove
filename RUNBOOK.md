# Runbook: Inserting Images into MinIO

This runbook guides operators and developers through adding backgrounds, character sprites, and writing studio artwork to MinIO so they appear in Decalove.

---

## 1. Overview & Architecture

Decalove serves visual assets directly through its FastAPI backend from an S3-compatible object store (MinIO).

- **Primary Bucket:** `decalove-assets` (configured via `MINIO_BUCKET_NAME` in `api/.env`).
- **Asset Routing:** The web client probes [`/api/v1/static/images/...`](file:///home/thirzq/decalove/api/app/routes/static_assets.py#L49-L69). The backend checks MinIO for key `static/images/...`.
- **Graceful Fallback:** If an image is not present in MinIO, the game displays a procedural CSS gradient generated from the location's color palette (see [`frontend/src/game/art.ts`](file:///home/thirzq/decalove/frontend/src/game/art.ts#L24-L35)). Sprites are omitted until present.
- **Immediate Effect:** As soon as an image is placed in MinIO under the expected key and served with an image MIME type (`image/png`, `image/jpeg`, `image/webp`), the game will display it.

---

## 2. Ports and Credentials

Check your deployment's active ports in [`api/.env`](file:///home/thirzq/decalove/api/.env#L151-L154):

| Service | Active Port (in `.env`) | Default Port | Internal Docker Port | Purpose |
| :--- | :--- | :--- | :--- | :--- |
| **MinIO Console** | `4531` | `9001` | `9001` | Browser management UI |
| **MinIO S3 API** | `4530` | `9000` | `9000` | S3 API endpoint for backend & `mc` |
| **Decalove API** | `4529` | `8000` | `8000` | FastAPI application |
| **Decalove Web** | `4528` | `80` | `80` | Web frontend / visual novel player |

- **Default Root User:** `minioadmin` (or `MINIO_ACCESS_KEY`)
- **Default Root Password:** `minioadmin` (or `MINIO_SECRET_KEY`)

---

## 3. Storage Layout & Naming Conventions

All assets must be stored inside the **`decalove-assets`** bucket using the following key patterns:

```
decalove-assets/
├── static/images/
│   ├── bg/
│   │   ├── <location_id>.png             # Default background for location
│   │   └── <location_id>_<time>.png      # Time-of-day specific background
│   └── characters/
│       ├── <character_id>.png            # Default fallback character sprite
│       └── <character_id>/
│           └── <expression>.png          # Expression-specific sprite
└── writing/
    └── library/                          # Writing Studio shared pictures
        └── <filename>.png
```

### A. Location Backgrounds (`static/images/bg/`)
- **Resolution:** 1280×720 (16:9 aspect ratio standard).
- **Format:** PNG or JPG.
- **Valid Location IDs:**
  `classroom`, `rooftop`, `library`, `school_gate`, `cafeteria`, `park`, `train_station`, `player_home`.
- **Valid Time Suffixes:**
  `morning`, `noon`, `afternoon`, `sunset`, `evening`, `night`.
- **Key Examples:**
  - `static/images/bg/classroom.png` (Default classroom; used in the opening scene)
  - `static/images/bg/classroom_sunset.png`
  - `static/images/bg/rooftop.png`
  - `static/images/bg/library_afternoon.png`

### B. Character Sprites (`static/images/characters/`)
- **Resolution:** Portrait orientation (e.g. 512×768) with transparent background.
- **Format:** PNG.
- **Valid Character IDs:**
  `aiko`, `ren`, `mika`, `haruto`.
- **Common Expressions:**
  `neutral`, `composed`, `happy`, `embarrassed`, `surprised`, `sad`, `annoyed`, `thoughtful`, `amused`.
- **Key Examples:**
  - `static/images/characters/aiko.png` (Fallback sprite for Aiko)
  - `static/images/characters/aiko/composed.png`
  - `static/images/characters/aiko/happy.png`
  - `static/images/characters/ren/amused.png`

### C. Writing Studio Shared Library (`writing/library/`)
- Any image placed under `writing/library/` (e.g., `writing/library/rooftops-at-dusk.jpg`) is immediately selectable in the Writing Studio's "+ Image" picker.

---

## 4. Procedures: How to Upload

### Procedure A: Via the MinIO Web Console (GUI)

1. Open your browser and navigate to:
   - **`http://localhost:4531`** (or `http://localhost:9001` if using default ports).
2. Sign in with your credentials (`minioadmin` / `minioadmin`).
3. Under **Buckets**, select **`decalove-assets`**. (If the bucket does not exist, click **Create Bucket** and name it `decalove-assets`).
4. Click **Create new path** to create the folder hierarchy:
   - Path: `static/images/bg/` or `static/images/characters/aiko/`
5. Navigate into the target path and click **Upload** -> **Upload File**.
6. Select your image file (e.g., `classroom.png`).
7. Verify the uploaded object key is `static/images/bg/classroom.png`.

---

### Procedure B: Via Docker MinIO Client `mc` (CLI)

Because the `decalove-minio` container already includes the MinIO Client `mc`, no host installations are required.

1. **Configure the internal `mc` alias:**
   ```bash
   docker exec decalove-minio mc alias set local http://localhost:9000 minioadmin minioadmin
   ```

2. **Ensure the bucket exists:**
   ```bash
   docker exec decalove-minio mc mb --ignore-existing local/decalove-assets
   ```

3. **Upload an individual file:**
   ```bash
   # 1. Copy your local file into the container
   docker cp ./classroom.png decalove-minio:/tmp/classroom.png

   # 2. Copy the file into the MinIO bucket with the correct object key
   docker exec decalove-minio mc cp /tmp/classroom.png local/decalove-assets/static/images/bg/classroom.png
   ```

4. **Upload an entire directory structure:**
   If you have a local directory structured like:
   ```
   assets/
   ├── bg/
   │   └── classroom.png
   └── characters/
       └── aiko.png
   ```
   Run:
   ```bash
   docker cp ./assets/. decalove-minio:/tmp/artwork/
   docker exec decalove-minio mc cp --recursive /tmp/artwork/ local/decalove-assets/static/images/
   ```

5. **List bucket contents to verify:**
   ```bash
   docker exec decalove-minio mc ls --recursive local/decalove-assets/static/images/
   ```

---

### Procedure C: Bulk Upload via Python Script

Decalove includes a built-in upload utility in [`generate_frontend_images.py`](file:///home/thirzq/decalove/generate_frontend_images.py).

1. Place your organized images in a directory (for example, `frontend/public/images/bg/` and `frontend/public/images/characters/`).
2. Run the script with `--upload-only`:
   ```bash
   api/.venv/bin/python generate_frontend_images.py --upload-only --source frontend/public/images
   ```

Alternatively, use a Python script with the `minio` library:

```python
from minio import Minio

# Use port 4530 for active .env port, or 9000 for standard Docker default
client = Minio(
    "127.0.0.1:4530",
    access_key="minioadmin",
    secret_key="minioadmin",
    secure=False,
)

bucket = "decalove-assets"
if not client.bucket_exists(bucket):
    client.make_bucket(bucket)

# Upload background image
client.fput_object(
    bucket,
    "static/images/bg/classroom.png",
    "./classroom.png",
    content_type="image/png",
)
print("Uploaded successfully.")
```

---

## 5. Verification Checklist

1. **Verify object metadata in MinIO:**
   ```bash
   docker exec decalove-minio mc stat local/decalove-assets/static/images/bg/classroom.png
   ```
   Verify that `Content-Type` is `image/png` or `image/jpeg`.

2. **Verify API HTTP Response:**
   ```bash
   # Test against the API port (4529 in active .env, or 8000)
   curl -sI http://localhost:4529/api/v1/static/images/bg/classroom.png
   ```
   *Expected result:* `HTTP/1.1 200 OK` and `content-type: image/png`.

3. **Verify in the Web Client:**
   Open the browser at `http://localhost:4528` (or your configured web port).
   - Start a game session.
   - The opening scene (Classroom) should now render your uploaded image rather than the fallback color gradient.

---

## 6. Troubleshooting

- **API returns `404 Not Found`:**
  - Verify that the key in MinIO starts with `static/images/`. A file stored at `bg/classroom.png` will return 404 because the API looks for `static/images/bg/classroom.png`.
  - Check the health check endpoint: `curl -s http://localhost:4529/health`. Ensure `"assets": "minio"` is reported.
- **Browser shows gradient even though API returns 200:**
  - The client caches asset probe results in memory during a session. Perform a hard refresh in the browser (`Ctrl+Shift+R` or `Cmd+Shift+R`).
  - Verify the file name matches the ID exactly in lowercase (e.g., `classroom.png`, not `Classroom.png`).
- **Browser refuses to render image:**
  - Check that the `Content-Type` is `image/png` or `image/jpeg`, not `application/octet-stream`. If necessary, re-upload setting the MIME type explicitly.
