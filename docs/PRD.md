# PRD — Decalove: AI-Directed Visual Novel Game

> Source of truth for product scope. This revision (2026-08-29) describes the product
> **as it is currently built** — the original brief's internal contradictions (§10 vs §24
> Rule 1, §14 vs §15) are resolved in the spec itself, and every place engineering
> interprets or extends this document is recorded in
> [`ARCHITECTURE.md`](./ARCHITECTURE.md).

## 1. Product Overview

**Decalove** is an AI-directed visual novel built with **Ren'Py** (client) and **FastAPI**
(story engine). The player reads dialogue and picks options like any visual novel — and
can also *type what they want to do* in natural language. An AI story engine turns that
into story: it keeps four characters' relationships and memories straight, directs pacing
and tension from live game state, and generates the next batch of beats **ahead of the
player's visible progress**, so the seams never show.

Unlike a conventional visual novel with a fixed branching tree, Decalove uses an **AI
Agent Story Engine** that generates each run of beats from:

- Player input (a chosen option or typed prose)
- Previous story events and the current scene
- Character personalities and authored world content
- Character relationships and emotional state
- World state (location, time, day, arc, flags)
- Character memories, retrieved semantically
- The Director's computed direction (pacing, tension, stances)
- Player style accumulated across the playthrough

The MVP ships **one authored world** — High School Romance / Slice of Life — with four
characters, eight locations, five story arcs, and three possible endings.

The goal is to make the game feel like a traditional handcrafted visual novel while
providing the adaptability of an AI-driven RPG.

---

# 2. Product Vision

> **"A visual novel where the story is written for you, not just played by you."**

Decalove combines:

**Visual Novel + AI Director + LLM + Image Generation + Player Choice + Dynamic Storytelling**

The player should feel that:

> "The game understands what I want to do and turns my decision into a real story."

The AI should not feel like a chatbot. It operates behind the scenes as the game's
**director, writer, narrator, and world simulator** — and the engine, not the model, owns
the state.

---

# 3. Goals

### Primary Goals

1. Deliver a Ren'Py visual novel whose story is directed at runtime by an AI engine.
2. Allow players to influence the story using natural language as well as choices.
3. Dynamically generate story progression using an LLM through OpenRouter.
4. Generate character/background imagery via OpenRouter image models **or** a local
   Stable Diffusion XL pipeline on GPU.
5. Maintain persistent character relationships, world state, and character memories.
6. Pre-generate a batch of **20 story steps** around each player decision, with the
   decision point placed at step 10–15 so generation overlaps playback.
7. Hide AI generation latency behind normal visual-novel gameplay.
8. Make generated content feel coherent: authored world, validated state, engine-owned
   pacing.
9. Support branching narratives without developers defining every branch.
10. Give a playthrough a real ending, earned by the player's choices over 300+ steps.

### Secondary Goals

- Replayability: the same input at different relationship values produces different scenes.
- Multiple relationship paths: romance, friendship, or neither.
- Offline playability: the whole game runs with no API key, no Docker, and no GPU.
- AI-generated side events and character secrets surfacing organically.
- Eventually: more worlds, player-created characters (the world registry is the seam).

---

# 4. Non-Goals

The current version does **not** attempt to:

- Generate a game engine dynamically — Ren'Py owns presentation, the backend owns story.
- Generate arbitrary gameplay mechanics.
- Allow unrestricted image generation without moderation and caching.
- Generate unlimited story content synchronously — every model call happens off the
  request path.
- Replace Ren'Py's dialogue/scene system entirely.
- Allow the LLM to execute code, control infrastructure, or become the source of truth
  for game state.

The AI operates through a controlled **Game State API** (§22).

---

# 5. Target Platform & Runtime

### Client

- **Ren'Py** application, runnable from the Ren'Py launcher; web build is the deployment
  target (the client uses only `renpy.fetch` + `im.Data`, so nothing needs the filesystem).

### Backend

- Python / FastAPI, async throughout
- MongoDB (persistence), MinIO (object storage) — both optional; offline fallbacks exist
- OpenRouter (chat + image models), local SDXL pipeline (images), deterministic
  placeholder image generator (offline)
- Hashed-n-gram embeddings by default; any OpenAI-compatible embeddings endpoint as a
  drop-in upgrade
- In-process asyncio background tasks (no Redis queue) for the single-node MVP

---

# 6. The MVP World: High School Romance

One authored world ships in the MVP: **`highschool_romance` — "Decalove: Second Year,
Second Chances"**.

**Premise.** You have transferred into Class 2-B six weeks into the school year — exactly
long enough for everyone else to have decided who they are. Four people are about to
decide what you are to them.

**Tone.** Warm slice-of-life romance with real stakes; funny more often than dramatic;
earned quiet moments. Rated **teen**.

### Cast

| id | Name | Age | Pronouns | Role | Starting relationship |
|---|---|---|---|---|---|
| `aiko` | Aiko Serizawa | 17 | she/her | class representative, runs the student council on spite and green tea | affection 12, trust 18, respect 30, familiarity 20 |
| `ren` | Ren Hoshikawa | 18 | they/them | art club president who never finishes a canvas | affection 8, trust 14, friendship 25, familiarity 28 |
| `mika` | Mika Todoroki | 17 | she/her | track team ace, one step from oversleeping | affection 10, trust 12, friendship 30, familiarity 22 |
| `haruto` | Haruto Amemiya | 18 | he/him | library aide, reads three books at once | affection 5, trust 8, respect 15, familiarity 10 |

Each character carries an authored personality, speech pattern, appearance, likes and
dislikes, a **secret** (never told to the player directly), a closed set of **expressions**
(which bounds what art can exist), and a two-colour **palette** (which the client uses to
draw a consistent placeholder sprite). The starting values are deliberately uneven: an
absolute-score ending would hand a passive player a Ren friendship ending for free.

### Locations

Eight locations, each with a prose description, an art direction string, a palette, the
**times of day it supports**, and authored **ambient lines** (in-world filler narration
played while the engine writes):

`classroom` (Class 2-B), `rooftop`, `library`, `school_gate`, `cafeteria` (noon only),
`park` (Riverside Park), `train_station`, `player_home` (Your Room).

### Story arcs

A playthrough moves through five authored arcs, one per **60 delivered steps**:

```
prologue → first_weeks → festival → summer → resolution
```

Each arc carries an authored note about what it is *for* (first impressions; routines;
a deadline in the air; unstructured time; consequences arriving). Without this, a long
save would be an undifferentiated series of nice conversations.

### Endings

A playthrough ends in one of three endings (§28): **romance**, **friendship**, or
**solo**. Which one you get is decided by how far you *moved* each character from their
authored baseline — not by absolute scores.

---

# 7. Core Gameplay Loop

The fundamental loop is:

```text
Player enters game
        v
Game loads current world state
        v
Visual Novel presents scene (server-authored opening, 20 steps)
        v
Player reads dialogue
        v
Player chooses an option
        OR
Player enters natural-language action
        v
Director parses intent and plans the next run (deterministic)
        v
Narrative Agent generates a 20-step batch:
        steps 1-9     reaction to the player's action, scene-building
        step 10-15    ONE decision point (choice menu or free-text prompt)
        steps 16-20   continuation beats that play while the next batch generates
        v
Validator repairs and commits the batch
        v
Visual Agent computes cache keys; missing art generates in the background
        v
Player reads steps 16-20 while the next batch generates
        v
Player answers the next decision point
        v
Cycle repeats
```

The critical design principle is:

> **AI generation happens ahead of the player's visible progress whenever possible.**

---

# 8. Player Experience

## 8.1 Starting a Game

Character setup is three questions, asked in Ren'Py:

```text
What should everyone call you?          (free text)
Which pronouns should the story use?     (she/her · he/him · they/them)
What kind of second year do you want?    (warm · dramatic · gentle)
```

The API also accepts an optional `romance_focus` (a character id) at creation; the
current client does not ask for it. **New Game is instant**: the opening scene is
authored, not generated, so the player never waits on a model for the first screen.

## 8.2 Continuing a Game

Ren'Py saves store only the `game_id`. Loading re-fetches the live game state from the
server — a save is a **bookmark**, not a rewind point. If the server has since collected
the save (stories uncontinued for a week are deleted), the client shows a dedicated
"This story has closed" screen instead of a connection error.

---

# 9. Story Interaction

The player interacts two ways.

## Method A — Traditional Choices

A decision point offers **3–5 options** (guaranteed by the validator). Example:

> Aiko looks at you nervously.
>
> "Are you really going to the festival tomorrow?"

```text
1. "Of course. I wouldn't miss it."
2. "Maybe. Why?"
3. "Only if you're going."
```

## Method B — Natural Language

The choice screen carries a permanent **"Say something else..."** button, and a `prompt`
step is a deliberate open question. The player types:

```text
"I tell Aiko that I'll go if she promises to stay with me."
```

The Director parses this into a bounded intent — an *attempt*, never an *outcome*:

```json
{
  "action": "invite_character",
  "target": "aiko",
  "emotion": "affectionate",
  "risk": "medium",
  "summary": "Kai tries to invite Aiko along"
}
```

The Narrative Agent then determines what actually happens. The player does **not**
directly control the narrative outcome — an attempt may be rebuffed, and whether it can
be is the Director's call (§15).

---

# 10. Batch Generation System

This is the core mechanic, and it supersedes the original brief's "ten-step generation".

When the player submits a decision, the backend does **not** generate one response. It
generates **one run of up to 20 steps**, shaped like this:

```text
Step 1   Aiko becomes surprised.
Step 2   She asks whether you are serious.
...
Step 14  [DECISION POINT — the player answers here]
Step 15  The light shifts; the conversation settles.
Step 16  "We should stay focused, but... thank you."
...
Step 20  The immediate scene continues.
```

The rules that define a batch:

1. **Exactly one decision point**, placed between step 10 and step 15 of the batch.
   The model is free to put it anywhere in that window (step 14 is typical); the
   validator guarantees there is exactly one — an extra decision point is converted to
   a plain beat, a missing one is inserted at step 15.
2. **Steps before the decision** develop the reaction to the player's previous action
   and build the scene toward the decision.
3. **Steps after the decision** (e.g. 16–20) are narration and dialogue that continue
   the immediate scene. They are written **before** the player answers the decision, so
   they must hold for any of the offered options — the choice's consequences land in the
   *next* batch. Their job is to give the engine 5 beats of cover while it generates.
4. **Player agency is never narrated.** The model never writes the player's decision,
   speech, or deliberate action (§24 Rule 1). The decision point hands control back;
   the engine decides what actually happens next.

The batch is committed to a **story queue** (§14); the player only ever sees one step at
a time. When the player answers the decision at step 14, the next batch starts generating
in the background while steps 15–20 are still queued — that overlap is what makes the
generation invisible.

---

# 11. Hidden Generation

The AI generation process should be invisible. The player should never see:

```text
Generating story...
Calling LLM...
Generating image...
```

Instead:

- **Playback never blocks on a model.** `POST /actions` and `POST /choices` return `202`
  immediately; generation runs in background tasks.
- **The client long-polls.** `GET /steps/next?wait_ms=` holds the connection briefly so
  the first beat of a batch arrives the instant it exists.
- **Ambient beats fill the gap.** While a batch is in flight, the server returns the
  current location's authored ambient lines ("The wind moves through the fence and keeps
  going.") and the client plays one as narration — cycling, never the same line twice in
  a row. After a cap the client stops pretending and says the story is catching up,
  because a fifth filler line reads as a hang.
- **The static opening.** The client ships an authored, art-complete first day
  (20 beats, local static images) so the very first scene plays with zero latency.

---

# 12. Generation Pipeline

```text
Player Input (choice or free text)
     v
DecisionContext (what they chose AND what they declined)
     v
Director.plan()  —  deterministic: pacing, tension, focus characters,
     |              stances from live relationship values, allow_failure,
     |              push_location, arc note, player-style note
     v
Memory recall (scoped to the directive's focus)
     v
Narrative Agent  —  one LLM call, strict JSON schema
     v
Validation Agent —  repair, then truncate
     v
Story queue (append-only ledger; committed but state not yet applied)
     v
Visual Agent    —  normalise visual spec, compute cache keys
     v
Asset Service   —  cache hit, or background generation (OpenRouter / SDXL)
     v
Ren'Py plays the batch while the next one generates
```

State is **committed when a step is delivered to the player, not when it is generated**
(§35). An unread run has changed nothing, which is what makes discarded and speculative
runs safe.

---

# 13. Story Step Schema

Every generated step follows a strict schema. The wire shape the LLM returns is a
strict-mode JSON Schema (§24); the domain shape is:

```json
{
  "type": "dialogue",
  "location": "rooftop",
  "characters": ["aiko"],
  "narration": "The wind gently moves through the rooftop fence.",
  "dialogue": {
    "speaker": "aiko",
    "text": "You really came...",
    "emotion": "surprised"
  },
  "emotion": {"aiko": "surprised"},
  "relationship_changes": {
    "aiko": {"affection": 3, "trust": 1}
  },
  "flags_set": {"met_on_rooftop": true},
  "memory": {
    "character": "aiko",
    "text": "Kai came up to the rooftop to find her.",
    "importance": 0.7,
    "emotion": "gratitude"
  },
  "next_choices": [
    {"id": "choice_1", "text": "I promised I would."},
    {"id": "choice_2", "text": "You sounded like you needed someone."}
  ],
  "visual": {
    "background": "rooftop",
    "character": "aiko",
    "expression": "surprised",
    "time_of_day": "sunset"
  }
}
```

Step types: `narration`, `dialogue`, `transition` (moves the scene; the only way to
change location), `event`, `choice` (blocking), `prompt` (blocking, free text), and
`ending` (terminal; the engine owns it — the model cannot emit one, see §28).

Relationship changes are **deltas only, never absolute values**, clamped to ±5 per axis
per step. Big feelings are earned across several steps, not asserted in one.

---

# 14. Story Queue

The backend maintains an append-only **step ledger** with a delivery cursor:

```text
Game Session

steps:   step_00000 ... step_00119     (append-only ledger)
cursor:  102                            (last step DELIVERED)

Queue (generated, not yet read):

step_00103
step_00104
...
```

There is no second data structure to keep in sync — the queue is simply the slice after
the cursor. When the player answers the decision at step 14 of a batch, steps 15–20 are
still queued, and the next batch appends behind them: a rolling narrative buffer.

The queue is linear **within a run**. Branching happens **between runs** — the decision
point is the buffer boundary, which is what makes the §11 "hidden generation" promise
compatible with §15's dynamic branching.

---

# 15. Dynamic Branching

The story is not a static tree; it is a **state graph**.

```text
                +-- Romance
                |
Player - Event -+-- Conflict
                |
                +-- Mystery
```

The same event leads to different scenes depending on player choices, character
relationships, previous actions, personalities, and story flags. Concretely, the
Director computes a **stance** per character from live relationship values and hands it
to the writer:

```text
Player teases Aiko

affection 60 / trust 55  ->  "comfortable enough to tease";
                              conflict reads as playful; +affection +friendship

affection 20 / trust 10  ->  guarded, not receptive; the attempt is
                              allowed to fail; -trust +anger
```

Therefore, the same player input can produce different results — and the same stance
drives both the real model (via the DIRECTION prompt block) and the offline scripted
narrator (via its parallel rebuff bank), so the behaviour holds with no API key.

---

# 16. Character Relationship System

Each character carries relationship values on nine axes:

```text
affection  trust  respect  fear  jealousy
friendship  romance  familiarity  anger
```

Values are integers 0–100, initialised from the authored starting values (§6), changed
only by validated per-step deltas (±5 max), and applied when a step is delivered. They
are **not shown to the player** — they shape the writing, stances, tension, and the
ending. A character's current emotion is also tracked per step.

---

# 17. Character Memory

Characters remember important player actions. The Narrative Agent proposes a memory on a
step (`character`, `text`, `importance` 0–1, `emotion`); the engine embeds it and stores
it **when the step is delivered** — an unread or discarded run leaves no trace.

Retrieval happens on every generation: memories are embedded and ranked by a blend of

```text
0.60 × semantic similarity (cosine over embeddings)
0.30 × authored importance
0.10 × recency
```

scoped to the characters the directive says are carrying the run. The default embedder
is a deterministic hashed-n-gram vectoriser (no key, no network); any OpenAI-compatible
embeddings endpoint can be configured instead (§22).

---

# 18. Image Generation

Images are generated for each scene from a structured **visual spec** (`background`,
`character`, `expression`, `pose`, `time_of_day`, `weather`, `mood`, `composition`),
normalised by the Visual Agent: an invented expression falls back to the character's
resting face, a bad background id falls back to the step's location, and the sprite set
stays closed.

Three image backends exist:

| Backend | What it is |
|---|---|
| `openrouter` | OpenRouter's unified image endpoint (default model `google/gemini-3.1-flash-image`) |
| `sdxl` | Local `stabilityai/stable-diffusion-xl-base-1.0` on a CUDA GPU via diffusers — no API key, no per-image cost, weights stored in the repo's `api/models/` |
| `placeholder` | Deterministic gradient PNG derived from the scene's authored palette — used when generation is off or fails |

Prompts are built deterministically from authored content — character appearance,
location art direction, expression, pose, time of day, and the world's art style
("anime visual novel key art, soft cel shading, warm rim light") — so the same scene
always produces the same prompt. Generated art is stored (MinIO or local files) and
referenced by the story step; steps are served even when their art is still pending, and
the client draws the authored placeholder until the real image lands.

---

# 19. Image Reuse

The system avoids generating duplicate images. Before requesting a new image:

```text
Compute content-derived cache key
        v
Key found in asset repository?
   v             v
  YES           NO
   v             v
Reuse       Generate + store
```

The cache key hashes the full scene identity — world, location/character, expression,
pose, time of day, weather, composition — so the second rooftop-at-sunset scene costs
nothing. Keys are shared across **all games in the world**, bounded by the world's
combinatorics rather than by how many sessions exist. The asset repository is keyed by
`cache_key`; generated art is never garbage-collected, because deleting it would only
make the next player regenerate it.

---

# 20. Visual Novel Presentation

The Ren'Py client owns presentation; the backend owns the story. The client is one loop:
ask for the next beat, show it, and when the beat is a decision point, hand control back.
It is responsible for:

- Dialogue box and speaker name colours (tinted with each character's palette)
- Backgrounds and character sprites — generated art over HTTP (`im.Data`), local static
  art when shipped, procedural gradient placeholders otherwise
- Transitions, the choice menu (options + "Say something else..."), the free-text input
- Save/load (storing only the game id), the offline screen, the "story has closed" screen
- Playing ambient lines while a batch generates

The AI never directly manipulates the Ren'Py runtime; everything crosses the Game API.

```text
Ren'Py Client
     v
Game API (/api/v1)
     v
AI Story Engine
```

---

# 21. AI Agent Architecture

Decalove uses multiple logical agents rather than one giant prompt:

| Agent | Responsibility |
|---|---|
| **Director** | Parse free text into a bounded intent (LLM when a key exists, keyword parser otherwise/on failure); then **plan** the next run deterministically — pacing, tension, focus characters, stances, `allow_failure`, location pressure, arc/style notes, and the finale gate |
| **Narrative** | Generate one run of beats from the DECISION + DIRECTION + ACTION prompt, under a strict JSON schema; route everything through the validator |
| **Scripted Narrator** | The offline provider *and* the failure fallback — a deterministic template narrator over the authored world, with a parallel rebuff bank driven by the same stances |
| **Validator** | Enforce the §24 rules: repair (clamp, rewrite, drop) before truncate; guarantee exactly one decision point and 3–5 choices |
| **Visual** | Normalise the visual spec, derive the cache keys, build prompts (§18/§19) |
| **Memory** | Embed, store, and retrieve character memories (§17) |
| **Safety** | Deterministic content screen on player input and model output (§29) |
| **Ending** | Choose which ending a playthrough has earned (§28) |

World state and character state are **engine-owned models**, not agents (§35).

---

# 22. Backend Architecture

```text
                    +--------------+
                    |    Ren'Py    |
                    | Web Client   |
                    +------+-------+
                           |
                           v
                    +--------------+
                    |   FastAPI    |
                    |  Game API    |
                    +------+-------+
                           |
          +----------------+----------------+
          v                v                v
     Game State        AI Agents        Asset Pipeline
     (MongoDB or       (LLM via         (MinIO or
      in-memory)        OpenRouter)      local files)
          |                                 |
          v                                 v
     character memories               generated images
     (embedded, cosine               (cache-keyed, reused)
      retrieval)
```

Every external dependency sits behind a protocol with a working offline implementation,
so the game runs with **no API key, no Docker, and no GPU**:

| Seam | With infrastructure | Offline default |
|---|---|---|
| Narrative | OpenRouter, structured outputs | Scripted narrator |
| Intent parsing | OpenRouter | Keyword parser |
| Images | OpenRouter or local SDXL | Deterministic placeholder PNG |
| Sessions | MongoDB | In-memory (lost on restart) |
| Art storage | MinIO | Local filesystem (`var/assets/`) |
| Embeddings | OpenAI-compatible HTTP | Hashed n-grams |

Background generation runs on in-process `asyncio` tasks with a per-game lock; `GET
/health` reports which backend each seam resolved to.

---

# 23. API Design

All routes are under `/api/v1`.

### World & games

```http
GET    /health                          which backends resolved; session GC state
GET    /worlds                          the authored world: cast, locations, palettes, ambience
POST   /games                           new game -> 201, opening scene ready immediately
GET    /games                           list game ids
GET    /games/{game_id}                 world state, character states, queue depth
GET    /games/{game_id}/save            the §30 save payload
DELETE /games/{game_id}                 delete a game
```

### Playback

```http
GET    /games/{game_id}/steps/next?wait_ms=   next beat; holds briefly when a batch is in flight
POST   /games/{game_id}/actions               free text -> 202 {batch_id}, generates in background
POST   /games/{game_id}/choices               a VN choice -> 202 {batch_id}
```

`GET /steps/next` returns one of four statuses — the client's whole loop is answering
them:

```json
{"status": "ready",           "step": {...}, "queue_depth": 3}
{"status": "pending",         "ambience": ["The wind moves through the fence."]}
{"status": "awaiting_player", "step": {...}}   // a decision point re-offered
{"status": "ended",           "step": {...}}   // carries the closing beat
```

### Assets

```http
GET /assets/{asset_id}         asset metadata
GET /assets/{asset_id}/view    raw image bytes (immutable cache headers)
```

### Legacy

`/scenes`, `/images`, and `/seed` are authored-scene CRUD routes that predate the story
engine; they talk to MongoDB directly and return 503 when it is down.

---

# 24. AI Generation Request

The backend hands the LLM structured context. The **system prompt** is identical for
every call in a world (the world sheet, cast, valid expressions, locations, and the hard
rules) — keeping it separate from the per-turn state is what makes prompt caching
worthwhile. The **user message** carries:

```text
PLAYER
    Kai (they/them); preferred story tone: warm; romantic interest: undecided

CURRENT WORLD STATE
    Day 14 (Wednesday), sunset, weather clear. Location: rooftop. Present: aiko.

CHARACTER STATES
    Aiko Serizawa [affection 52, trust 61, ...] feeling embarrassed

RELEVANT MEMORIES
    - [aiko] Kai defended Aiko during the school conflict. (importance 0.92)

STORY SO FAR
    (rolling one-line summaries of each batch)

RECENT STEPS
    (the last 20 delivered steps, verbatim)

DECISION
    The player chose: "Only if you're going."
        They were also offered, and passed on: "..."

DIRECTION (from the engine, derived from live state -- follow it)
    Pacing: building (tension 58/100)
    This run should: let the attempt land and change something modest
    - aiko is comfortable enough to tease. affection 52, trust 61 ...

PLAYER ACTION
    Parsed as: action=invite_character, target=aiko, tone=affectionate, risk=medium
    Attempt: Kai tries to invite Aiko along
```

The model must return a strict-mode JSON object — exactly 20 steps, exactly one decision
point between steps 10 and 15, deltas within ±5, visuals from the closed expression and
location sets.

---

# 25. Agent Rules

The AI must follow several hard constraints (the validator enforces them regardless of
what the model returns):

### Rule 1 — Player Agency

The AI must never force the player to perform an action unless the action was already
explicitly chosen. Bad: *"You kiss Aiko."* Better: *"Aiko moves closer, waiting to see
what you will do."* Player-voiced dialogue and player-acting narration are stripped or
truncated.

### Rule 2 — Character Consistency

Behaviour must match the cast sheet and the character's current emotional and
relationship state. A low-trust character does not suddenly confide. Unknown characters
are dropped.

### Rule 3 — World Consistency

Only authored locations exist. The scene stays put unless a `transition` step moves it;
a teleport is snapped back. The engine's clock only moves forward, through time slots
the destination actually supports.

### Rule 4 — State Consistency

Relationship changes are deltas, never absolute values, never beyond ±5 per axis per
step. The engine owns reserved flags (`ending`, `ending_partner`, `ended`) — the model
cannot forge them.

### Rule 5 — Narrative Continuity

Each step follows from the one before it and from the established facts. Memory
proposals are bounded (importance 0–1) and only stored on delivery.

### Output contract

Exactly 20 steps; exactly one decision point at step 10–15; 3–5 genuinely different
choices (fewer than 3 real options is worse than none — use a `prompt` instead);
every step carries a visual from the closed sets.

---

# 26. Generation Latency Strategy

LLM generation and image generation may be slow. Decalove uses:

### Batch pre-generation

The next 20-step batch is generated when the player answers a decision point — while
steps 16–20 of the current batch are still queued.

### Continuation beats

The 5 post-decision steps are written to hold for any choice, buying the engine cover
without pre-generating branches that would be thrown away.

### Long-polling

`GET /steps/next?wait_ms=` delivers the first beat the instant it exists (server cap:
10s; client asks for 4s; the client's fetch timeout is always the wait plus a margin).

### Ambient beats

While a batch is in flight, the client plays the location's authored ambient lines —
never a spinner (§11).

### Asset caching

A cache hit costs nothing; a miss never blocks the story — the step ships with a
`pending` asset and the client draws the placeholder.

### Offline speed

With no API key, the scripted narrator generates a full batch in microseconds, so the
same pipeline hides latency perfectly offline.

---

# 27. Failure Handling

The game must never become unplayable because an AI request failed.

```text
LLM unavailable / times out / returns unrepairable output
        v
Scripted narrator writes the run instead (marked fallback)
        v
Game continues; the player never sees an error
```

- If a batch fails to commit, the decision point is **re-offered** (`awaiting_player`) —
  the right recovery, not a dead end.
- If the queue runs dry without a decision point, the engine self-heals with a low-key
  `auto` continuation.
- If image generation fails, the step is served with the asset marked `unavailable` and
  the client draws its consistent placeholder sprite/background.
- If the backend is unreachable, the client shows a readable offline screen after a few
  retries — and distinguishes "server down" from "this save was collected" (§8.2).

---

# 28. Endings

A playthrough finishes. The requirements:

1. **A floor, not a threshold.** The story may only end after **more than 300 delivered
   steps** (five arcs at 60 steps each). Nothing used to set `ended`, so the story was
   literally infinite — and an ending that can arrive at any moment is worse than none.
2. **The model cannot end your game.** The wire schema's step type is a six-value
   literal without `ending`; only the Director's finale gate (never on an idle `auto`
   turn) can open the way, and the engine **promotes** the last step of the finale run
   into an `ending` step itself — dropping the decision point models staple on out of
   habit.
3. **Earned, not scored absolutely.** The Ending Agent ranks characters by growth
   against their authored baseline:

   ```text
   romantic = romance + affection      platonic = friendship + trust
   growth   = max(romantic, platonic) − 2 × anger,  measured against the starting values
   ```

   Anger is doubled deliberately: with deltas capped at ±5, anger 60 takes a dozen
   deliberately hostile beats. Below a growth floor of 20 the ending is **solo** — which
   is not a failure state, it is what "I never got close to anyone" looks like. Ties
   break on the romance focus named at setup, then who the player sought out most, then
   trust, then id — fully deterministic.
4. **The offline narrator writes endings too**, because it is also the fallback: a
   timeout on the very last run must not hand the player another choice forever.

`session.ended` flips when the ending step is **delivered**, like every other state
change.

---

# 29. Content Safety

Because the system dynamically generates content, safety exists at multiple layers:

```text
Player Input
      v
SafetyFilter (deterministic pattern screen; prompt-injection detection)
      v
LLM Generation (world's authored safety boundaries in the system prompt)
      v
Validator (per-step content screen before the run is committed)
      v
Game
```

The screen blocks sexual content, self-harm, graphic violence, hate, dangerous
real-world instructions, and minor sexualisation. The design bias is to **contain**
rather than punish: blocked player input is absorbed in-world ("the moment passes
without anything being said") instead of becoming an error the player argues with, and
an attempt to talk to the model rather than the character is treated the same way.

The world carries its own authored boundaries, handed to every generation call: all
characters are high-school students, romance stays at the level of a network TV teen
drama, no self-harm or substance use, no real people or brands, and distress is handled
with care.

The filter is deliberately small — it is the first line, not a substitute for a hosted
moderation model, and is written so one can be layered in front of it later.

---

# 30. Save System

The server-side save is the whole `GameSession`: player profile, world state (location,
clock, flags, inventory, arc, events), character states (all nine axes + emotion), the
step ledger and cursor, pending batch, history, intent, player style, and the previous
directive.

The client-facing save payload (`GET /games/{id}/save`):

```json
{
  "game_id": "...",
  "world_id": "highschool_romance",
  "current_step": 103,
  "story_arc": "festival",
  "world_state": {},
  "character_states": {},
  "flags": {},
  "inventory": [],
  "queue": ["step_00104", "step_00105"],
  "asset_ids": [],
  "memories": []
}
```

Ren'Py saves persist only the `game_id` and re-attach to the server on load.

---

# 31. Session Lifetime & Cleanup

Stories the player has not continued for **7 days** are deleted, along with their
character memories. Two guarantees:

- **Finished stories are never collected** — someone who got through 300 steps to an
  ending keeps it forever.
- **Generated art is never collected** — assets are shared across all games and keyed
  by content, so there is no per-game subset to delete.

"Not continued" is measured by a dedicated **play clock** (`last_played_at`), stamped
only when the player actually advances the story — background batch commits and asset
back-fills do not count, so a save nobody is playing looks abandoned even while the
engine is busy with it. An application sweeper runs on an interval, re-checks expiry
under the per-game lock, and never races a returning player.

---

# 32. MVP Scope

### Implemented

- One world: High School Romance / Slice of Life (§6)
- 4 characters, 8 locations, 5 arcs, 3 endings
- Traditional choices (3–5 options) and natural-language input
- AI-generated story (OpenRouter) with full offline fallback
- 20-step batch generation with a mid-batch decision point
- Character relationship system (9 axes) and character memory (embeddings + retrieval)
- Dynamic scene generation and AI-generated images (OpenRouter **or** local SDXL)
- Image reuse via content-derived cache keys
- Save/load (bookmark model), session GC, health endpoint
- Authored static opening on the client (local art, zero latency)

### Not yet

- Multiple worlds and player-created characters (the registry is the seam)
- Speculative branch prefetch (implemented behind a config flag, off by default)
- Ren'Py web build and on-device playtesting (static checks stand in)

---

# 33. MVP User Flow

```text
Launch
   v
Intro card -> character setup (name, pronouns, tone)
   v
New Game -> opening scene is ready instantly
   v
First day plays (authored, 20 steps, decision at step 14)
   v
Player answers the decision -> next batch generates behind steps 15-20
   v
Story continues, one decision every ~15 beats
   v
Arcs advance (prologue -> first_weeks -> festival -> summer -> resolution)
   v
Step 301+ -> the story may close -> romance / friendship / solo ending
   v
Ending screen -> main menu (save kept forever)
```

---

# 34. Success Metrics

### Engagement

- Average session duration
- Average number of story steps per session
- Number of player interactions (choices vs typed input ratio)
- Returning players
- Stories completed (an ending reached)

### AI Quality

- Story continuation acceptance rate
- Player regeneration rate
- Contradiction rate
- Invalid generation rate (validator violations per batch)
- Character consistency score

### Performance

```text
New game (opening scene):          instant (authored)
Step retrieval (queued step):      < 500 ms
Long-poll wait:                    up to 4 s client / 10 s server
Background batch generation:       < 20 s preferred
Image generation:                  asynchronous; never blocks dialogue
```

---

# 35. Future Features

### Multiplayer Stories

Multiple players influence the same AI-generated world.

### User-Generated Characters & Custom Worlds

Players define name, personality, appearance, background, and relationship preferences;
worlds beyond high school (fantasy, cyberpunk, horror, sci-fi, mystery). The world
registry (`app/content/registry.py`) is the designed seam.

### Voice Acting & Music Generation

Generated dialogue converted to speech; dynamic music driven by emotion, location,
tension, and relationship state.

### Real moderation model

A hosted classifier layered in front of the deterministic safety screen.

### Speculative prefetch

Pre-generating a run per branch so choices resolve instantly — implemented behind
`SPECULATIVE_PREFETCH_MAX_BRANCHES` (default 0); costs one model call per option.

---

# 36. Technical Principle

The most important architectural principle is:

> **The LLM generates the narrative, but the game engine owns the state.**

Do not allow the LLM to become the source of truth. Instead:

```text
GameSession (MongoDB or memory)
      v
Source of Truth
      v
AI receives state (prompt context)
      v
AI proposes changes (deltas, flags, memories, visuals)
      v
Validator checks and repairs changes
      v
Backend commits changes -- on DELIVERY, not on generation
```

This prevents the AI from accidentally changing the game's rules — and it is what makes
branching, speculation, and discard safe: a run nobody read has changed nothing.

The second principle, from the original brief, still defines the product:

> **An AI agent continuously directs a visual novel around the player's actions while
> the player experiences it as a seamless, pre-rendered narrative.**
