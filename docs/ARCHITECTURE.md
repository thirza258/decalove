# Decalove — Architecture & Decisions

Companion to [`PRD.md`](./PRD.md). The PRD says *what* the product is; this file records
*how* it is being built, every place the implementation deviates from the PRD, and why.

Status: **living document** — updated as the implementation lands.

---

## 1. Two contradictions in the PRD, and how they are resolved

These are not nitpicks. Both determine the shape of the story queue, so they had to be
settled before any schema was written.

### 1.1 §10 (ten-step generation) contradicts §24 Rule 1 (player agency)

§10's worked example contains:

```
3. Player confirms.
8. Player responds.
```

That is the AI scripting the player's actions — which §24 Rule 1 forbids in the same
document ("Bad: *You kiss Aiko.*").

**Resolution — a run halts at the first point that requires player agency.**

A generated batch is not ten steps that auto-play. It is *up to* `STEPS_PER_BATCH` steps
that **terminate in exactly one blocking step**, where a blocking step is a `choice`
(traditional VN options) or a `prompt` (free-text natural-language input). The engine never
narrates a player decision; it hands the decision back.

This is encoded in the schema (`StepType.is_blocking`) and enforced by the validator, not
left to the playback loop to discover.

So §10's example run becomes:

```
1. Aiko becomes surprised.
2. She asks whether you are serious.       <- dialogue
3. [CHOICE] "I mean it." / "...Maybe."     <- run ends here; player acts
```

and the remaining beats are generated *after* the player answers, conditioned on what they
chose. A run is often shorter than ten steps. That is correct behaviour, not a shortfall.

### 1.2 §14 (flat rolling queue) contradicts §15 (dynamic branching)

§14 describes a linear buffer `step_103 … step_112` with generation refilling at
`step_108`. But §15 says the same input can lead to different states. If the buffer holds
104–112 and the player picks `choice_2` at 103, those nine steps were generated against an
assumption that no longer holds.

**Resolution — a choice point *is* the buffer boundary.** The queue is linear only within a
run. Branching happens between runs. This falls straight out of §1.1 above.

To keep §11's "hidden generation" promise without pre-generating branches that get thrown
away, latency is hidden three ways instead:

1. `POST /actions` and `POST /choices` return `202` immediately; generation runs in the
   background.
2. `GET /steps/next` supports short long-polling (`?wait_ms=`), so the client receives the
   first step the instant it exists rather than on a poll boundary.
3. When the buffer is empty and a batch is in flight, the client plays an *ambient beat*
   (an in-world line of narration drawn from the current location) instead of a spinner.
   The player never sees "Generating story…".

**Speculative branch prefetch** — generating a run for each choice in parallel *before* the
player picks — is implemented behind `SPECULATIVE_PREFETCH_MAX_BRANCHES`, which defaults to
`0` (off). It multiplies LLM cost by the number of choices; that is the operator's call,
not a default.

---

## 2. Deviations from the PRD's suggested stack

The PRD hedges these as "Suggested architecture" (§5) and "Potential implementation" (§17).
The committed code already chose differently, and that choice is kept.

| PRD suggests | Built | Why |
|---|---|---|
| PostgreSQL | **MongoDB** (existing `docker-compose.yml`) | Already the committed choice; the story-step ledger is document-shaped. Persistence sits behind a repository protocol, so Postgres remains a swap, not a rewrite. |
| pgvector / vector DB | **In-process cosine similarity** over stored embeddings | MongoDB 7 *community* has no `$vectorSearch` — that is Atlas-only, and the compose file runs the community image. At MVP scale (4 characters, tens of memories per session) a full scan is faster than a network hop and removes an infra dependency. |
| Redis + background workers | **In-process `asyncio` tasks** behind a `GenerationQueue` seam | One less service for a single-node MVP. The seam is where arq/Celery/Redis goes when the game runs on more than one worker process. |
| Object storage / CDN | **MinIO**, with a local-filesystem store as fallback | MinIO was already committed. The local store means the game runs with no Docker at all. |

**Embeddings**: OpenRouter is a chat/completions gateway and does not expose an embeddings
endpoint. The default embedder is a deterministic hashed-n-gram vectoriser (pure Python, no
key, no network) — good enough for "did the player defend Aiko?"-grade lexical recall at MVP
scale. `EmbeddingProvider` is a protocol; an OpenAI-compatible HTTP embedder can be dropped
in via config.

---

## 3. Runtime seams

Every external dependency is behind a protocol with a working offline implementation, so
the whole game is playable with **no API key, no Docker, and no Ren'Py SDK**.

| Seam | Real | Offline default |
|---|---|---|
| `ChatProvider` | OpenRouter (`response_format: json_schema`) | `ScriptedNarrator` — a deterministic template narrator |
| `ImageProvider` | OpenRouter image models | Deterministic generated placeholder PNG |
| `EmbeddingProvider` | OpenAI-compatible HTTP | Hashed-n-gram |
| `GameRepository` | Motor / MongoDB | In-memory dict |
| `AssetStore` | MinIO | Local filesystem |

`ScriptedNarrator` earns its place twice: it is the offline provider **and** it is the §26
fallback narrative used when the real LLM errors or returns unrepairable output. The game
degrades to "less interesting" rather than "broken".

---

## 4. The state ownership rule (§33)

The LLM proposes; the backend commits. Concretely:

* The LLM emits `GeneratedStep` — no ids, no asset URLs, no absolute stat values.
* Relationship changes are **deltas only**, clamped to `±MAX_RELATIONSHIP_DELTA` per step.
  A model that asks for `affection: +60` gets `+5` and a logged violation.
* The backend assigns `step_id`, `index`, and resolves visuals.
* **State is committed when a step is *delivered* to the player, not when it is generated.**
  This is what makes speculative and discarded runs safe: an unplayed run can never move a
  relationship value.

### Steps are immutable once stored

A 300-step save is deep-copied on every repository read, and a four-second long poll does
about 33 of them. Measured, that was ~2.9 ms per copy at 400 steps — ~98 ms of event-loop
CPU per poll, per player, spent copying steps that were then discarded.

`StoryStep` is therefore frozen, and `InMemoryGameRepository._clone` deep-copies only the
mutable head, sharing the steps behind a fresh list: **98 ms → 0.74 ms**, and flat in step
count. Freezing is what makes the sharing *provably* safe rather than incidentally safe.
Amend a stored step with `step.model_copy(update={...})` and put the result back in the
ledger — `GeneratedStep` stays mutable, since the validator repairs those before they ever
become a `StoryStep`.

---

## 5. The generation pipeline

One turn is more than "send the player's words to a model". The engine decides the
*shape* of the scene first, deterministically, and the model writes inside that shape.

```
player picks an option  ─┐
player types a line     ─┼─► DecisionContext ─┐
queue ran dry           ─┘   (kind, chosen,   │
                              rejected, typed)│
                                              ▼
              CharacterState ──────────► Director.plan()  ◄── PlayerStyle
              WorldState     ──────────►      │            ◄── last Directive
              step ledger    ──────────►      │
                                              ▼
                                          Directive
                          (pacing, tension, focus, stances,
                           beat_goal, allow_failure, push_location)
                                              │
                     ┌────────────────────────┴────────────────────┐
                     ▼                                             ▼
            memory recall (scoped to                    prompt: DECISION +
            the directive's focus)                      DIRECTION + ACTION
                     │                                             │
                     └──────────────► Narrative Agent ◄────────────┘
                                              │
                                          Validator
                                              ▼
                                        story queue
```

### The decision is not just what they picked

`DecisionContext` records *how* the player answered, and each kind renders differently
in the prompt:

| Kind | What the writer is told |
|---|---|
| `choice` | the line they picked **and the ones they declined** — "they passed on X and Y" |
| `free_text` | their exact words, plus an instruction to honour their specifics rather than smoothing them into a generic beat; flagged separately when options were on offer and they wrote their own anyway |
| `auto` | nobody acted; keep it small, introduce nothing, hand control straight back |
| `opening` | establish the place and the people |

The rejected options are the part usually thrown away. Three lines were offered, the
player took one — the two they left say something, and the writer can let them register
as absence.

### The Director plans; the model writes

`DirectorAgent.plan()` is deterministic and makes no model call. Handing "what should
happen next" to the LLM as well would leave nothing owning pacing across a playthrough.
It derives:

* **Stances** — how each character is disposed *right now*, from live relationship
  values. This is PRD §15 made concrete: teasing Aiko at affection 60 / trust 55 gets
  `conflict_mode: playful`; at affection 20 / trust 10 it gets `serious`, and she is
  marked not receptive. The stance note quotes the actual numbers so the model can
  calibrate rather than guess.
* **Tension** (0–100) from the attempt's risk, the focus characters' anger and jealousy,
  and their trust. Typing a risky move yourself counts for more than picking it off a
  menu; an unprompted continuation counts for less.
* **Pacing** — `quiet` / `building` / `charged` / `release`. A charged run is *always*
  followed by a release run: two peaks back to back means neither one lands.
* **`allow_failure`** — whether the attempt may be rebuffed. Scoped to the character it
  is aimed at, not to any bystander who happens to be in the room.
* **`push_location`** — after ~12 beats in one place, suggest a move that fits the time
  of day. Never during a charged run.
* **Player style** — a rolling profile (writes vs picks, bold vs cautious, who they keep
  returning to) so the writing can meet the player where they are.

### The world moves on its own

Two things advance without the player asking, because otherwise the directive would be a
constant:

* **The clock.** A `transition` step moves `time_of_day` forward along
  `morning → noon → afternoon → sunset → evening → night`, snapping to a slot the
  destination actually supports (the cafeteria is noon only; your room is evening,
  night, morning). When nothing is left today, the day rolls and the weekday follows.
  Monotonic by construction — it only ever looks forward. This is also what keeps the
  time-keyed asset cache of PRD §19 honest: without it every rooftop scene for the life
  of a save would resolve to one cached sunset.
* **The arc.** `prologue → first_weeks → festival → summer → resolution`, on a delivered-
  step cadence (`STEPS_PER_ARC`, default 60), recording each arc it leaves in
  `completed_events`. Each arc carries its own authored note in DIRECTION — four of the
  five were unreachable while the arc never advanced.

The scripted narrator emits real `transition` steps (on a move, or when the directive
pushes a location), so this works with no API key. A move is never rebuffed: walking
somewhere is not an offer anyone can decline.

### It changes the offline game too, not just the prompt

The scripted narrator carries a parallel **rebuff bank**: what each beat looks like when
it does *not* land, per family and per character. Selected by the same stance the model
would have received. Without it the offline narrator would be relentlessly agreeable and
relationship state would be invisible with no API key.

```
"I tell Aiko she is hopeless at this"

  affection 60 / trust 55        affection 20 / trust 10
  pacing building, tension 69    pacing charged, tension 78
  AIKO: "I am going to           AIKO: "Is that supposed
  remember that. I keep           to be funny."
  records."
  +affection +friendship         -trust +anger
```

A rebuff is still remembered — being turned down is at least as memorable as being
accepted — with its own memory text and importance.

---

## 6. Endings, and the 300-step gate

A playthrough now finishes. Nothing used to set `session.ended`, so the story was
literally infinite; and an ending that can arrive at any moment is worse than none, so
the requirement is a *floor*: **more than 300 delivered steps** before the story may
close.

### The model is not allowed to end your game

`StepType.ending` is terminal but not blocking — `is_blocking` and `is_terminal` used to
be the same idea, and they come apart exactly here: an ending stops the run without asking
the player anything, so `awaiting_player` must stay false.

The obvious risk is a model that decides to wrap things up at step 40. Three layers stop
it, and the first one makes the other two belt-and-braces:

1. **`LLMStep.type` is a six-value `Literal`, not `StepType`.** The strict schema is built
   once in `NarrativeAgent.__init__`, so if `ending` were in that enum it would be legal
   on every request forever. Narrowing the wire type means the format cannot express an
   ending at all.
2. **`Directive.is_finale` is the only gate**, set by `DirectorAgent.plan()` — never on a
   `DecisionKind.auto` turn, because a story should not close itself while the player is
   idle. It reaches the validator as `allow_ending`.
3. **Reserved flags.** `_commit_step` merges `flags_set` straight into world state, so
   `ending`, `ending_partner` and `ended` are stripped from anything the model proposes
   and written by the engine at commit time.

The finale run is written like any other run — the model gets a DIRECTION block saying
*this is the last one, close it* — and the **engine promotes it**: `_promote_ending` drops
the decision point models staple on out of habit, and marks what is left as the ending.
Safety screening has already run per-step by then, so the closing prose is checked like
everything else.

`session.ended` flips in `_commit_step`, on **delivery**, like every other state change.

### Which ending you get

`app/agents/ending.py` ranks characters by **growth against their authored baseline**, not
by absolute values. That matters in this world: Ren opens at friendship 25 / trust 14 and
Aiko at friendship 0 / trust 18, so an absolute threshold would hand a passive player a Ren
ending and punish someone who spent the whole game earning Aiko's trust from lower down.

```
romantic = romance + affection      platonic = friendship + trust
growth   = max(romantic, platonic) - 2 x anger,  measured against starting_relationship
```

Anger is doubled deliberately: deltas cap at ±5 a step, so anger 60 takes a dozen
deliberately hostile beats, and a love story with someone furious at you is the wrong story
to tell about that playthrough. Below a growth floor of 25 the ending is `solo` — which is
not a failure state, it is what "I never got close to anyone" looks like. Ties break on the
romance the player named at setup, then who they sought out most, then trust, then id.

`ScriptedNarrator.finale()` writes all three endings offline, because it is also the
failure fallback: if only a working model could produce a finale, a timeout on the very
last run would hand the player another choice and the story would never end.

### The deadlock a long playthrough found

Building this exposed a real flaw in the stance system. Low trust made a character
unreceptive, unreceptive meant every attempt was rebuffed, and a rebuff earned no trust —
so a player could spend 300 steps on Aiko and move nothing but `familiarity`. **Every**
playthrough ended `solo`.

The fix is a `thawing` stance: `trust < 25` but `familiarity >= 45` is receptive. Time
spent together is a way in. A focused playthrough now reads as an arc rather than a wall:

```
step   5   trust 18   guarded, everything bounces
step 125   trust 34   thawing
step 245   trust 69
step 305   trust 86   ->  friendship ending with Aiko
```

Only a 300-step test could surface that, which is why `tests/test_long_playthrough.py`
plays the whole game rather than mocking it.

---

## 7. Decisions: 3-5 options, every 3-5 clicks

`Validator` is the single choke point — `NarrativeAgent._finish()` routes the authored
opening, the LLM run *and* the scripted fallback through one `validate()` call — so the
guarantee lives there and nowhere else.

* An over-long list is **capped** at `MAX_CHOICES` (5).
* A short list is **topped up** from an authored bank to `MIN_CHOICES` (3). The old
  behaviour, converting a short list into a free-text prompt, is gone: a thin menu is the
  model under-delivering, and answering that by taking the menu away from the player is a
  strange punishment. `StepType.prompt` goes back to meaning *a deliberate open question*.
* Dedupe is punctuation-insensitive, so "I promised." and "I promised!" are one option.
* Top-ups name the character in the scene but are **not** stance-aware: `validate()`
  receives no `Directive`, so it cannot know whether the beat went well, and a filler that
  leaned warm after a rebuff would actively misrepresent the scene.

`STEPS_PER_BATCH` dropped from 10 to 5, so a decision arrives every 3-5 clicks rather than
every ten. That is a tightening of the §1.1 reading of PRD §10, not a contradiction of it:
a run was always *up to* N steps stopping at the first decision.

---

## 8. Garbage collection

A story nobody has continued for a week is deleted, along with its character memories.

**`updated_at` is the wrong clock.** `repo.save()` touches it on every write, and most
writes are background: a batch committing, a failed-batch marker, an asset back-fill
landing long after the player quit. A save could look "played" with nobody near it. So
`GameSession.last_played_at` is a **play clock**, stamped in exactly three places — a step
actually delivered, and the two player-input paths. Reads stay pure, which matters because
a monitoring script polling `GET /games/{id}` would otherwise keep every save alive forever.

**Finished stories are never collected.** Somebody got through 300 steps to reach that
ending; deleting it a week later is the worst thing this feature could do. An ended session
is also a fixed-size document that does not grow.

**Generated art is never touched.** Assets are keyed by a content-derived `cache_key`,
shared across every game in the world, and bounded by the world's combinatorics rather than
by session count — there is no per-game subset to delete, and deleting one would only make
the next player regenerate it.

**An application sweeper, not a MongoDB TTL index.** A TTL fires inside `mongod` and
cascades to nothing, so every expired save would leave its memories behind with no owner
left to find them by; it also does not exist on the in-memory backend, which would break
the offline seam and make the feature untestable without Docker.

`MaintenanceService` owns its own `asyncio` task — deliberately *not* registered with
`GenerationService._tasks`, because that set is what `drain()` waits on and an endless loop
in it would make every drain hang. Deletion happens under the same per-game lock every
other mutation takes, and re-checks expiry **under that lock**: the scan is not atomic, and
a player who came back in between must not lose their save.

On the client, a collected save is not the same thing as a dead server. `decalove_resume()`
tells them apart without parsing status codes out of `FetchError` text: if `/worlds` still
answers, the server is up and the save is what is gone — and the player gets
`decalove_expired` ("This story has closed") rather than being sent to restart uvicorn.

---

## 9. The Ren'Py client

Ren'Py owns presentation; the backend owns the story (PRD §20). The client is one loop:
ask for the next beat, show it, and when the beat is a decision point, hand control back.

```
game/decalove/
  00_config.rpy   API base URL, timeouts, rollback policy
  10_api.rpy      renpy.fetch wrapper - never raises, returns None on failure
  20_art.rpy      placeholder gradients + sprites, and im.Data for generated art
  30_state.rpy    boot, world cache, after_load re-attach
  40_screens.rpy  decision screen, offline screen
  50_player.rpy   the playback loop
game/script.rpy   entry point + character setup
```

### Verified against the Ren'Py docs

* `renpy.fetch(url, method=None, data=None, json=None, content_type=None, timeout=5,
  result='bytes', params=None, headers={})` works on desktop, mobile **and web**, and
  raises `FetchError` on failure.
* Called **outside** an interaction it repeatedly calls `renpy.pause()`, so it does not
  lock the game. Called **inside** one it blocks the display system. → every API call is
  made from a `python:` block, never from inside a screen.
* Generated images are shown with `im.Data(bytes, "hint.png")`, fed by
  `renpy.fetch(url, result="bytes")`. Nothing is written to disk, which matters because
  the web build's filesystem is a sandbox.

### Four decisions that are not obvious

**Rollback is off** (`config.rollback_enabled = False`). The server's step cursor only
moves forward. A player who rolled back three beats and then advanced would ask for "the
next step" and receive step N+1, not the one they rewound past — the transcript and the
world state would silently disagree from then on. Skip is off for the same reason: the
next beat may not exist yet.

**A save is a bookmark, not a rewind point.** Saves persist `decalove_game_id` and nothing
else; `after_load` re-fetches `GET /games/{id}`. So saving at step 10, playing to step 30
and loading that save resumes at **30**, not 10. That is the honest MVP answer — real
rewind needs server-side replay — and it beats serialising the step ledger into the save,
where it would immediately diverge from the server's copy.

**Fetch timeouts must exceed the long-poll window.** `renpy.fetch` defaults to 5s; the
client asks the server to hold `GET /steps/next` for up to 4s. Every call site passes
`timeout = wait_ms/1000 + 5`, so a slow-but-successful long poll cannot arrive as a
`FetchError` and be mistaken for failure. A test asserts this relationship holds.

**`except Exception` around a fetch is a trap.** Ren'Py's own control flow — quit, jump,
rollback, end-interaction — all derive from `Exception`, and `renpy.fetch` calls
`renpy.pause()` internally. A bare catch would swallow the player's attempt to quit
mid-request. The wrapper re-raises anything from `renpy.*` that is not `FetchError`.

### Hiding the latency (PRD §11)

The player never sees "Generating story…". While a batch is in flight `GET /steps/next`
returns `pending` plus the current location's ambient lines, and the client plays one as
narration — cycling so the same line never appears twice in a row. After
`DECALOVE_AMBIENT_LIMIT` of them the client stops pretending and says so, because at that
point a fifth "the wind moves through the fence" reads as a hang, not as atmosphere.

---

## 10. Testing

425 tests. The whole suite runs with **no API key and no Ren'Py SDK**; the integration
suites additionally want MongoDB and MinIO and skip themselves when those are down, so a
fresh clone with no Docker still gets a green run.

```bash
cd api && .venv/bin/python -m pytest -q
```

| Suite | Covers |
|---|---|
| `test_validator.py` | PRD §24 rules 1–5, repair-vs-truncate, content screen |
| `test_direction.py` | stances, tension, pacing, location pressure, player style, §15 branching |
| `test_prompts.py` | the DECISION / DIRECTION / ACTION blocks, placeholder expansion |
| `test_schema.py` | strict JSON Schema rules, DTO→domain conversion, fence tolerance |
| `test_agents.py` | intent parsing, scripted narrator, rebuff banks, cache keys, memory ranking |
| `test_llm_path.py` | **the OpenRouter branch**, via a stub provider |
| `test_openrouter_transport.py` | headers, retry policy, repair round-trip, image decoding |
| `test_generation_service.py` | the background cycle: failure, timeout, shutdown, asset write-back, speculation |
| `test_game_flow.py` | full sessions over HTTP, state ownership, save payload, self-heal |
| `test_runtime.py` | which implementation each seam resolves to |
| `test_embeddings.py`, `test_assets.py`, `test_edges.py` | cosine, PNG encoding, path traversal, error paths |
| `test_renpy_client.py` | every `python:` block compiles; labels/screens/transforms resolve |
| `test_client_contract.py` | client URLs and JSON field names against live responses |
| `test_ending.py` | ending selection, the 300-step gate, promotion and refusal |
| `test_maintenance.py` | the play clock, the sweep, the under-lock re-check, the loop |
| `test_long_playthrough.py` | **a whole 300+ step game to its ending**, over HTTP |
| `test_integration_*.py` | **real MongoDB and MinIO** — skipped automatically when they are down |

Two of these deserve calling out.

`test_llm_path.py` exists because every other test runs with no API key, which means the
code that actually ships — DTO parsing, the schema handed to the model, the repair
round-trip, and every fallback edge — would otherwise never execute. A stub `ChatProvider`
covers it without a key or a network.

`test_renpy_client.py` and `test_client_contract.py` exist because the SDK is not
installed, so the client cannot be launched. They check the two things that would
otherwise fail only on a real playthrough: Python blocks that do not compile, and drift
between the routes/fields the client reads and the ones the server sends.

The `test_integration_*.py` suites run against a real MongoDB and a real MinIO rather
than fakes. The interesting behaviour there is the optimistic-concurrency guard and
presigned URLs; a hand-rolled double would only test my reimplementation of them. They
skip themselves when the services are not running, so `pytest` still passes with no
Docker.

**The regression test worth keeping.** `test_answering_a_decision_never_re_offers_it_while_
generating` guards a bug that is invisible offline: right after a choice is submitted the
head of the ledger is still that same blocking step, so checking `awaiting_player` before
checking for an in-flight batch hands the player back the menu they just answered. With
the scripted narrator that never happens (generation finishes in microseconds); with a
real model at 5–20s it happens every single time. The test injects a slow narrative agent
to make the window real.

---

## 11. Deferred (needs something not available in this environment)

| Deferred | Blocked on | Notes |
|---|---|---|
| A run against a real LLM | `OPENROUTER_API_KEY` | The path is covered by a stub provider, not by a live call. Model ids in `.env.example` were checked against OpenRouter's live model list. |
| Real image generation | `OPENROUTER_API_KEY` + `IMAGE_GENERATION_ENABLED=true` | The pipeline runs end-to-end offline against a placeholder PNG generator, so caching, storage and delivery are exercised — only the model call is untested. |
| ~~MongoDB / MinIO integration~~ | — | **Done.** Both run under `docker compose`, with integration suites against them and a containerised API image. |
| Ren'Py build and playtest | Ren'Py SDK not installed | Static checks stand in (see §10). Nothing here has been seen on screen. |
| Multi-process generation queue | Redis, once there is more than one API process | The in-process `asyncio` tasks and per-game locks are correct for one node only. `MongoGameRepository` already raises `StaleSessionError` rather than losing a write. Two API processes sweeping for garbage at once is safe — the loser's under-lock re-check finds the session already gone — but they duplicate the scan. |
| Endings written by a real model | `OPENROUTER_API_KEY` | The gate, the promotion and the refusal are covered by tests; the *prose* of a model-written finale has only been exercised through the authored offline finale. |
| Speculative branch prefetch in anger | — | Implemented and off by default (`SPECULATIVE_PREFETCH_MAX_BRANCHES=0`); the cost/benefit needs a real model to judge. Branches are held in process memory and the unchosen siblings are discarded when the player commits, so the cache is bounded to one decision point — but an abandoned game leaves its last set behind until restart. |

---

## 12. Running it

```bash
# Backend - works with nothing else installed
cd api
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/uvicorn app.main:app --reload --port 8000
```

`GET /health` reports which backend each seam resolved to:

```json
{"status":"healthy","storage":"memory","assets":"local",
 "narrative":"scripted (no OPENROUTER_API_KEY)","images":"disabled"}
```

### With Docker

```bash
cd api
docker compose up -d                 # MongoDB + MinIO + the API on :8000
docker compose up -d mongodb minio   # infrastructure only, run the API locally
```

The compose file sets `STORAGE_BACKEND=mongo` and `ASSET_BACKEND=minio` for the
containerised API deliberately: both services are on the compose network, so a silent
fallback to in-memory storage there would mean a container that quietly loses every save.
Locally the default stays `auto`, which is what makes a bare clone runnable.

Add generated prose by putting an `OPENROUTER_API_KEY` in `api/.env` — compose passes it
through. None of it is required to play.

For the client, open the repo root in the Ren'Py launcher and press Launch. If the API is
not on `http://localhost:8000`, change `DECALOVE_API_BASE` in
`game/decalove/00_config.rpy`.
