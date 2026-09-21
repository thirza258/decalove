# Pictures, and where they live

Every picture a Decalove deployment shows comes out of the object store: character
sprites, backgrounds, and the illustrations writers insert in the Writing Studio. There
is no image volume mounted into the web container and, with `WEB_MODE=True`, nothing is
generated at runtime — so a picture that is not in MinIO is a picture nobody will see.
That is the trade: one place to put a file, one place to look when it is missing.

Art is never required. A missing background is drawn as the location's palette gradient
and a missing sprite is simply absent, so the game stays playable while you fill the
bucket in.

## The bucket

One bucket holds everything: `decalove-assets` by default (`MINIO_BUCKET_NAME`). With
the stack from `api/docker-compose.yml` the console is on <http://localhost:9001> and
the S3 API on <http://localhost:9000>, signing in with `MINIO_ACCESS_KEY` /
`MINIO_SECRET_KEY` from `api/.env` (`minioadmin` / `minioadmin` until you change them).

```
decalove-assets/
├── static/images/                        pictures you upload by hand
│   ├── bg/
│   │   ├── classroom.png                     any time of day
│   │   ├── rooftop_sunset.png                one time of day
│   │   └── library_night.png
│   └── characters/
│       ├── aiko.png                          the sprite used when nothing fits better
│       └── aiko/
│           ├── happy.png                     one expression
│           └── thoughtful.png
├── writing/
│   ├── library/                          the Writing Studio's shared pictures
│   │   ├── rooftops-at-dusk.jpg
│   │   └── notebook.png
│   └── <workspace-id>/
│       ├── images/<sha256>.png               pictures writers uploaded themselves
│       └── <document-id>/<sha256>.txt        manuscript exports and backups
├── backgrounds/<cache-key>.png           written by image generation, if it is on
└── characters/<cache-key>.png
```

Only the first two branches are yours to fill. The last two are the generator's own
cache and are keyed by prompt, not by name; `WEB_MODE=True` never writes them.

## What to name a file

`static/images/` is looked up by name, and the names are the world's own ids.

| Picture | Object key | Notes |
| --- | --- | --- |
| Background | `static/images/bg/<location_id>.png` | Used at every time of day |
| Background, one time of day | `static/images/bg/<location_id>_<time>.png` | `morning`, `noon`, `afternoon`, `sunset`, `evening`, `night` |
| Character sprite | `static/images/characters/<character_id>.png` | The fallback for every expression |
| Character expression | `static/images/characters/<character_id>/<expression>.png` | Preferred when the beat names that expression |

Locations in the shipped world are `classroom`, `rooftop`, `library`, `school_gate`,
`cafeteria`, `park`, `train_station` and `player_home`; characters are `aiko`, `ren`,
`mika` and `haruto`. Expressions are the emotion names the engine uses in a beat, such
as `neutral`, `happy`, `thoughtful`, `surprised`, `sad`, `embarrassed` or `annoyed`.

The exact key with the time of day wins over the plain one, and the expression file wins
over the character's fallback. Both clients look for `.png`, sprites read best with a
transparent background, and 1280×720 matches the stage the game is laid out on.

## Uploading

### With the MinIO console

1. Open <http://localhost:9001> and sign in.
2. Open **Object Browser → decalove-assets**. Create the bucket if the stack has never
   written to it (**Buckets → Create Bucket**, named `decalove-assets`).
3. Use **Create new path** to make `static/images/bg/`, then **Upload → Upload File**.
   The path you are standing in becomes the start of the object key, so uploading
   `classroom.png` into `static/images/bg/` gives `static/images/bg/classroom.png`.
4. Reload the game. A background appears the next time that location is on screen.

### With the `mc` command line

The MinIO container already has `mc` in it, so nothing needs installing:

```bash
cd api
docker compose cp ./artwork decalove-minio:/tmp/artwork      # a folder of PNGs
docker compose exec minio mc alias set local http://localhost:9000 minioadmin minioadmin
docker compose exec minio mc mb --ignore-existing local/decalove-assets
docker compose exec minio mc cp --recursive /tmp/artwork/ local/decalove-assets/static/images/
docker compose exec minio mc ls --recursive local/decalove-assets/static/images/
```

From a host that has `mc` installed, the same thing is two lines:

```bash
mc alias set decalove http://localhost:9000 minioadmin minioadmin
mc cp --recursive ./artwork/ decalove/decalove-assets/static/images/
```

`mc` sets the content type from the file extension. If you upload with something that
does not, set `image/png` or `image/jpeg` explicitly — browsers will not display an
object served as `application/octet-stream`.

### From the generator

`generate_frontend_images.py` writes each picture to MinIO as it makes it, under exactly
these keys. To upload an existing folder without generating anything:

```bash
python generate_frontend_images.py --upload-only
```

## Pictures for the Writing Studio

The studio has its own pictures, and they are ordinary objects in the same bucket.

**A shared library.** Anything under `writing/library/` is offered to every writer in
the deployment: they choose **+ Image → Shared library** and insert it without
uploading anything. Use plain, readable file names — the studio shows the file name and
uses it as the picture's first description.

```bash
docker compose exec minio mc cp ./rooftops-at-dusk.jpg local/decalove-assets/writing/library/
```

Only `.png`, `.jpg`, `.jpeg`, `.webp` and `.gif` are listed. Nothing else in the bucket
is reachable this way: the studio refuses any key outside `writing/library/`, and a
library picture is *referenced*, never copied, so replacing the object replaces the
picture everywhere it was inserted.

**What writers upload.** A picture inserted from a writer's own machine is stored at
`writing/<workspace-id>/images/<sha256>.<ext>`, named after its content, so the same
picture uploaded twice is one object. The document keeps only that identifier, and the
API serves the bytes back through `GET /api/v1/writing/workspaces/{id}/images/{id}` —
scoped to the workspace that holds them, `inline`, `nosniff`, and never through the
public game-art route. Uploads are PNG, JPEG, WebP or GIF up to 5 MB, and the first
bytes of the file have to match the type it claims, so an SVG or a renamed script is
refused rather than stored.

Deleting an object that a manuscript points at leaves a broken picture in that document,
showing its description instead. Workspace folders are safe to archive wholesale once
their writers are done.

## Checking your work

```bash
# the object is there, with the right content type
docker compose exec minio mc stat local/decalove-assets/static/images/bg/classroom.png

# the API serves it (200 and image/png)
curl -sI http://localhost:8000/api/v1/static/images/bg/classroom.png

# the studio can see the shared library
curl -s http://localhost:8000/api/v1/writing/library
```

If the API answers 404 for a key `mc stat` can see, check that the API is pointed at the
same bucket and endpoint (`MINIO_BUCKET_NAME`, `MINIO_ENDPOINT` — inside compose it is
`minio:9000`, not `localhost:9000`) and that `ASSET_BACKEND` resolved to `minio`:
`curl -s http://localhost:8000/health` reports the backend each seam actually chose. A 200 from the API
while the game still shows a gradient usually means the file name is not the location or
character id the world uses.
