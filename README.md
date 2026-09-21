# Decalove

> *A visual novel where the story is written for you, not just played by you.*

A visual novel for the web and Ren'Py, directed at runtime by an AI story engine. The
player reads dialogue and picks options like any VN — and can also just *type what they
want to do*. The engine turns that into story, keeps four characters' relationships and
memories straight, and generates the next run of beats behind the scenes so the seams
never show.

```
game/          Ren'Py client  - presentation, input, placeholder art
frontend/      React web client - the same story and player choices
api/           FastAPI engine - director, narrative, validator, memory, images
docs/PRD.md    the product spec
docs/ARCHITECTURE.md   how it is built, and every place it departs from the spec
docs/STORY.md  the chapter structure, character threads and writing standards
docs/IMAGES.md the object-store folder layout for art, and how to upload into it
```

The story follows a newcomer helping Class 2-B find its place through **A Place for Us**,
a festival postcard exhibit. A blue notebook connects five chapters: first impressions,
shared responsibilities, an imperfect festival, summer invitations, and promises worth
keeping. Each character has something different at stake, and the player can decide how
much to get involved. See the [story guide](docs/STORY.md).

## Run it

The web client also includes [writing courses and a script/novel studio](docs/WRITING.md):
18 detailed lessons, a rich-text manuscript editor, AI-assisted scenes with 50 dialogue
lines by default, MongoDB drafts and course progress, and MinIO exports and backups.

The backend runs with **no API key, no Docker, and no configuration**. In that mode the
prose comes from an authored scripted narrator rather than a model — the game is fully
playable, just not AI-written.

```bash
cd api
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/uvicorn app.main:app --reload --port 8000
```

Check what it resolved to:

```bash
curl -s localhost:8000/health
# {"status":"healthy","storage":"memory","assets":"local",
#  "narrative":"scripted (no OPENROUTER_API_KEY)","images":"disabled"}
```

Then open this repository in the **Ren'Py launcher** and press Launch.

For the web client, in another terminal:

```bash
cd frontend
npm ci
npm run dev
```

### Turning the AI on

```bash
cp api/.env.example api/.env
# set OPENROUTER_API_KEY=sk-or-...
```

### Or run the whole thing in Docker

```bash
./deploy.sh
```

Builds and starts everything — MongoDB, MinIO, Redis, the API, both Celery workers, and
the web client — then waits for them to report healthy and prints the URLs. The game
lands on <http://localhost:3000> and the API on <http://localhost:8000>.

| | |
|---|---|
| `./deploy.sh` | build and start everything |
| `./deploy.sh --gpu` | ...with local SDXL image generation on the GPU |
| `./deploy.sh --no-web` | API and workers only, for shipping the Ren'Py build instead |
| `./deploy.sh --no-build` | restart without rebuilding images |
| `./deploy.sh down` | stop everything, keeping saves and art |
| `./deploy.sh logs [service]` | follow logs |
| `./deploy.sh ps` | what is running |

The first build pulls a CUDA base image and installs Node and Python dependencies, so
give it a few minutes; `DECALOVE_WAIT_TIMEOUT=600 ./deploy.sh` raises the 300-second
health wait on a slow disk. Only the databases report health, so `./deploy.sh ps` is what
confirms the API and both workers actually stayed up.

It creates `api/.env` from `api/.env.example` on first run, which is where all
configuration lives — the script itself only starts things. `docker compose` directly
still works if you prefer; the script is that invocation with the flags remembered:

```bash
cd api && docker compose up -d
```

Locally, without Docker, MongoDB and MinIO are detected automatically — without them,
saves live in memory and generated art lands in `api/var/assets/`.

### Tests

```bash
cd api && .venv/bin/python -m pytest -q
```

The tests need no API key or Ren'Py SDK; the integration suites need
MongoDB and MinIO and skip themselves cleanly when those are not running.

Client checks, from `frontend/`: `npm test`, `npm run build`, and `npm run lint`.
Agent regression coverage includes provider timeouts, memory outages, retry idempotency,
choice boundaries, opening handoff, chapter progression and complete playthroughs.

## How it works

```
Player picks an option  ─┐
Player types a line     ─┼─►  DecisionContext ──►  Director.plan()  ◄── relationship state
Queue ran dry           ─┘    what they chose,          │              ◄── pacing memory
                              and what they               │            ◄── how they play
                              turned down                 ▼
                                                      Directive
                                        pacing · tension · who carries it ·
                                        each character's stance · may this fail?
                                                          │
                                                          ▼
                                      Narrative Agent ── one run of beats
                                                          │
                                      Validator ── PRD §24: repair, then truncate
                                                          │
                                      Story queue ── Ren'Py plays it while the
                                                     next run generates behind it
```

The main guarantees:

**The engine owns the state.** The model *proposes* relationship changes, flags and
memories; the backend validates, clamps and commits them — and only when a step is
actually delivered to the player. A generated run nobody read has changed nothing.

**Typed input plays the story; it never replaces it.** Free text is the point of the
game, so the engine classifies a typed line before anything is written: an act the
world cannot contain is *heard* rather than enacted, and an instruction to the game
("restart", "make this a zombie apocalypse") is absorbed as a non-action. Ordinary
attempts — including every one no menu offered — go through untouched.

**The story keeps a ledger.** Every delivered run is saved with the player's own words
for the move that caused it, and the prompt is given the first three scenes and the
last twelve — so a callback in the summer arc can still reach the prologue instead of
quietly forgetting it. The web client shows where you stand with everyone and flashes
what each beat changed.

**Choices divide consequences from anticipation.** A normal batch has up to 20 beats
and one decision, requested at steps 10–15. Any remaining beats stay in the same scene
and cannot change relationships, flags, emotions or memories. The next generated run
responds to the answer. Finales have no decisions anywhere in the run.

**The engine directs; the model writes.** Before anything is generated, the Director works
out the shape of the scene from live state — how tense it should be, who carries it, how
each character is currently disposed toward the player, and whether the attempt is allowed
to fail. Teasing Aiko at affection 60 is a playful argument; at affection 20 it costs you
trust. Same input, different scene, and it works with no API key at all.

**Failures have bounded recovery paths.** Each story provider has an attempt timeout.
Web mode tries its configured alternate AI models, then offers a retry of the same turn;
offline mode can use authored prose. Embedding outages fall back to local text retrieval,
and memory-index failures leave the proposal in the story ledger while playback continues.

**And it ends.** A playthrough runs for more than 300 steps before the story is allowed to
close, and which ending you get comes from how far you moved someone against where they
started — not from an absolute score. Spend the game on one person and you finish with
them; spread yourself thin and you finish alone.

Both of the first two resolve real contradictions in the PRD. See
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) §1, §6 and §8.
