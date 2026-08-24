# Decalove API — AI story engine

FastAPI backend for an AI-directed visual novel. The LLM writes the narrative; **this
service owns the state** (PRD §33).

Runs with no API key, no MongoDB and no MinIO — each of those is a seam with a working
offline implementation, and `/health` tells you which one is live.

## Quick start

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/uvicorn app.main:app --reload --port 8000
```

* Swagger: <http://localhost:8000/docs>
* Health:  <http://localhost:8000/health>

Or run everything in containers:

```bash
docker compose up -d                 # MongoDB, MinIO, and the API on :8000
docker compose up -d mongodb minio   # infrastructure only
docker compose logs -f api
```

The containerised API sets `STORAGE_BACKEND=mongo` and `ASSET_BACKEND=minio` on purpose:
both services are on the compose network, and a container that silently fell back to
in-memory storage would lose every save without saying so.

Optional AI:

```bash
cp .env.example .env          # then set OPENROUTER_API_KEY
```

## What resolves to what

| Seam | With infrastructure | Without |
|---|---|---|
| Narrative | OpenRouter, structured outputs | authored scripted narrator |
| Intent parsing | OpenRouter | keyword parser |
| Images | OpenRouter image models | deterministic placeholder PNGs (or off) |
| Sessions | MongoDB | in-memory (lost on restart) |
| Art storage | MinIO | `var/assets/` |
| Memory embeddings | any OpenAI-compatible endpoint | hashed n-grams |

The offline column is not a stub set — it is what the game runs on until you configure
otherwise, and it is what the test suite exercises.

## Game API

| Method | Endpoint | |
|---|---|---|
| `GET` | `/health` | which backends resolved, and the state of the session collector |
| `GET` | `/api/v1/worlds` | the authored world: cast, locations, palettes |
| `POST` | `/api/v1/games` | new game → opening scene is ready immediately |
| `GET` | `/api/v1/games` | list game ids |
| `GET` | `/api/v1/games/{id}` | world state, character states, queue depth |
| `GET` | `/api/v1/games/{id}/save` | PRD §27 save payload |
| `DELETE` | `/api/v1/games/{id}` | delete a game |
| `GET` | `/api/v1/games/{id}/steps/next` | next beat; `?wait_ms=` to long-poll |
| `POST` | `/api/v1/games/{id}/actions` | free text → **202**, generates in background |
| `POST` | `/api/v1/games/{id}/choices` | a VN choice → **202** |
| `GET` | `/api/v1/assets/{id}` | generated image metadata |
| `GET` | `/api/v1/assets/{id}/view` | raw image bytes |

Legacy authored-scene CRUD (`/scenes`, `/images`, `/seed`) predates the story engine and
still requires MongoDB; it returns **503** when Mongo is down rather than a 500.

### The playback contract

`GET /steps/next` returns one of four statuses, and the client's whole loop is answering them:

```json
{"status": "ready",           "step": { ... }, "queue_depth": 3}
{"status": "pending",         "ambience": ["The wind moves through the fence."]}
{"status": "awaiting_player", "step": { ...a choice or prompt... }}
{"status": "ended"}
```

`pending` means a batch is in flight. The client plays an ambient line — never a spinner.

## Layout

```
app/
  domain/       step schema, game state, memory, direction, validation results
  content/      the authored world (High School Romance)
  agents/       director (parse + plan), narrative, validator, visual, memory,
                safety, ending (which ending was earned),
                scripted (offline narrator + failure fallback)
  llm/          provider protocols, OpenRouter, strict JSON Schema, embeddings
  repositories/ Mongo + in-memory
  assets/       MinIO + local filesystem, tiny PNG encoder
  services/     game orchestration, background generation, asset lifecycle,
                maintenance (garbage collection of abandoned saves)
  routes/       HTTP
  runtime.py    composition root - probes every dependency at startup
tests/          425 tests; integration suites skip themselves without Docker
```

## Tests

```bash
.venv/bin/python -m pytest -q
```

See [docs/ARCHITECTURE.md](../docs/ARCHITECTURE.md) §6 for what each suite covers and why
the LLM-path and Ren'Py-client suites exist.
