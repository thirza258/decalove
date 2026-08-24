# Decalove

> *A visual novel where the story is written for you, not just played by you.*

A Ren'Py visual novel whose scenes are directed at runtime by an AI story engine. The
player reads dialogue and picks options like any VN — and can also just *type what they
want to do*. The engine turns that into story, keeps four characters' relationships and
memories straight, and generates the next run of beats behind the scenes so the seams
never show.

```
game/          Ren'Py client  - presentation, input, placeholder art
api/           FastAPI engine - director, narrative, validator, memory, images
docs/PRD.md    the product spec
docs/ARCHITECTURE.md   how it is built, and every place it departs from the spec
```

## Run it

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

### Turning the AI on

```bash
cp api/.env.example api/.env
# set OPENROUTER_API_KEY=sk-or-...
```

### Or run the whole thing in Docker

```bash
cd api && docker compose up -d      # MongoDB + MinIO + the API on :8000
```

Locally, MongoDB and MinIO are detected automatically — without them, saves live in
memory and generated art lands in `api/var/assets/`.

### Tests

```bash
cd api && .venv/bin/python -m pytest -q
```

425 tests. None of them need an API key or the Ren'Py SDK; the integration suites need
MongoDB and MinIO and skip themselves cleanly when those are not running.

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

Two things hold it together:

**The engine owns the state.** The model *proposes* relationship changes, flags and
memories; the backend validates, clamps and commits them — and only when a step is
actually delivered to the player. A generated run nobody read has changed nothing.

**Every run ends where the player takes over.** A run is not ten beats that auto-play; it
is up to ten beats that stop at the first moment requiring a decision. That is what keeps
the AI from writing the player's lines for them, and it is what makes branching safe.

**The engine directs; the model writes.** Before anything is generated, the Director works
out the shape of the scene from live state — how tense it should be, who carries it, how
each character is currently disposed toward the player, and whether the attempt is allowed
to fail. Teasing Aiko at affection 60 is a playful argument; at affection 20 it costs you
trust. Same input, different scene, and it works with no API key at all.

**And it ends.** A playthrough runs for more than 300 steps before the story is allowed to
close, and which ending you get comes from how far you moved someone against where they
started — not from an absolute score. Spend the game on one person and you finish with
them; spread yourself thin and you finish alone.

Both of the first two resolve real contradictions in the PRD. See
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) §1, §6 and §8.
