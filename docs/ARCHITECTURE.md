# Decalove — Architecture & Decisions

Companion to [`PRD.md`](./PRD.md). The PRD says *what* the product is; this file records
*how* it is being built, every place the implementation interprets or extends the PRD,
and why.

Status: **living document** — updated as the implementation lands. This revision reflects
the working tree as of 2026-08-29 (20-step pipelined batches, local SDXL images, static
opening in progress).

---

## 1. Contradictions in the original brief, and how they are resolved

The original brief contained two internal contradictions. Both determined the shape of
the story queue, so they were settled before any schema was written. The resolutions
below are baked into the PRD as written (§10, §14).

### 1.1 "Ten steps" (original §10) contradicts player agency (original §24 Rule 1)

The brief's worked example contained *"3. Player confirms."* and *"8. Player responds."*
— the AI scripting the player's actions, which Rule 1 of the same document forbids
("Bad: *You kiss Aiko.*").

**Resolution — the batch contains exactly one decision point, and the model never writes
past it.** A batch is not N steps that auto-play. It is a run of up to
`STEPS_PER_BATCH` steps with **exactly one blocking step** (a `choice` menu or a
`prompt`), and the engine guarantees the invariant by construction:

- The wire schema (`LLMStep.type`, a six-value `Literal`) is built once in
  `NarrativeAgent.__init__` and handed to the model on every request — the model cannot
  express anything the enum does not contain.
- The validator converts any *extra* decision point to a plain beat, inserts one at
  step index 14 if the model produced none, and truncates the run at `STEPS_PER_BATCH`.

The engine never narrates a player decision; it hands the decision back.

### 1.2 A flat rolling queue (original §14) contradicts dynamic branching (original §15)

A linear buffer `step_103 … step_112` with refill at `step_108` cannot coexist with "the
same input produces different results": if the player picks `choice_2` at 103, the nine
queued steps were generated against an assumption that no longer holds.

**Resolution — the decision point is the buffer boundary.** The queue is linear only
within a run; branching happens between runs. This falls straight out of §1.1: state is
committed on *delivery* (§4), so a run generated against a branch nobody took can simply
be discarded — there is nothing to roll back.

**Speculative branch prefetch** — generating a run per choice *before* the player picks
— is implemented behind `SPECULATIVE_PREFETCH_MAX_BRANCHES` (default `0`, off). It
multiplies LLM cost by the number of choices; that is the operator's call, not a
default. Note: with the current 20-step batch shape the speculation trigger (the tail of
the ledger being a choice step) no longer fires — the tail is always a continuation
beat. The mechanism is intact but dormant until either the flag is on *and* a batch
ends on a choice, or the trigger is revisited. It costs nothing to keep: a lost
speculation costs one regeneration, never correctness.

---

## 2. Deviations from the brief's suggested stack

The brief hedged these as "Suggested architecture" / "Potential implementation". The
committed code chose differently, and those choices are kept.

| Brief suggests | Built | Why |
|---|---|---|
| PostgreSQL | **MongoDB** | Committed from the start; the story-step ledger is document-shaped. Persistence sits behind a repository protocol, so Postgres remains a swap, not a rewrite. |
| pgvector / vector DB | **In-process cosine similarity** over stored embeddings | MongoDB 7 *community* has no `$vectorSearch` (Atlas-only), and the compose file runs the community image. At MVP scale (4 characters, tens of memories per save) a full scan is faster than a network hop and removes an infra dependency. |
| Redis + background workers | **In-process `asyncio` tasks** behind a `GenerationService` seam | One less service for a single-node MVP. The seam is where arq/Celery/Redis goes when the game runs on more than one worker process. |
| Object storage / CDN | **MinIO**, with a local-filesystem store as fallback | MinIO was committed; the local store means the game runs with no Docker at all. |
| Image models via OpenRouter only | **Three image backends**: OpenRouter, local SDXL on GPU, deterministic placeholder | Local SDXL (stabilityai/stable-diffusion-xl-base-1.0 via diffusers) removes per-image API cost and works with no key; the placeholder keeps the whole pipeline exercisable with nothing installed. The provider is chosen by `IMAGE_BACKEND`. |
| Ten-step generation | **20-step batches, decision point at step 10–15** | See §5. |

**Embeddings**: OpenRouter is a chat/completions gateway and does not expose an
embeddings endpoint. The default embedder is a deterministic hashed-n-gram vectoriser
(unigrams + bigrams, sublinear term frequency, L2-normalised, blake2b-bucketed — not
Python's `hash()`, which is salted per process and would make stored embeddings
unreadable after a restart). Good enough for "did the player defend Aiko?"-grade
lexical recall at MVP scale. `EmbeddingProvider` is a protocol; an OpenAI-compatible
HTTP embedder drops in via config.

**Structured outputs**: OpenRouter forwards `response_format: {type: json_schema, …,
strict: true}` to providers that support it. Strict mode has rules Pydantic's default
output violates (`additionalProperties: false` on every object, everything `required`
with nullability carrying optionality, no `default` keyword), so `strict_schema()`
rewrites the schema, and a separate **DTO layer** (`app/llm/dto.py`) replaces every
open-ended `dict[str, X]` with a list of entries — `dict` maps are illegal under strict
mode. The wire shape and the domain shape are deliberately different models;
`LLMRun.to_domain()` converts. `OPENROUTER_REQUIRE_PARAMETERS` keeps the request off
provider endpoints that would silently ignore `response_format`, and one **repair
round-trip** is attempted on unparseable JSON (hand the model its own broken output and
the error, temperature 0.2) before falling back.

---

## 3. Runtime seams

Every external dependency is behind a protocol with a working offline implementation, so
the whole game is playable with **no API key, no Docker, no GPU, and no Ren'Py SDK**.

| Seam | Real | Offline default |
|---|---|---|
| `ChatProvider` | OpenRouter (`response_format: json_schema`) | `ScriptedNarrator` — deterministic template narrator |
| Intent parsing | OpenRouter | Keyword parser (regex lexicon), also the failure fallback |
| `ImageProvider` | OpenRouter image models / local SDXL | Deterministic gradient placeholder PNG |
| `EmbeddingProvider` | OpenAI-compatible HTTP | Hashed-n-gram |
| `GameRepository` | Motor / MongoDB | In-memory dict |
| `AssetRepository` | MongoDB (unique `cache_key` index) | In-memory dict |
| `AssetStore` | MinIO | Local filesystem, served via the API's proxy route |

`runtime.py` is the composition root: it probes each backend once at startup
(`STORAGE_BACKEND=auto`, `ASSET_BACKEND=auto`) and either uses it or falls back with a
loud warning; `mongo`/`minio` values **fail startup** instead of silently degrading,
because a container that quietly loses every save is worse than one that fails loudly.
`GET /health` reports the resolution:

```json
{"status":"healthy","mongodb":false,"world":"highschool_romance",
 "storage":"memory","assets":"local",
 "narrative":"scripted (no OPENROUTER_API_KEY)","images":"disabled",
 "embeddings":"hashing","steps_per_batch":20,"speculative_branches":0,
 "ending_after_steps":300,"session_gc":{...}}
```

`ScriptedNarrator` earns its place twice: it is the offline provider **and** the PRD §27
failure fallback when the real LLM errors, times out, or returns something the validator
cannot repair. The game degrades to "less interesting" rather than "broken" — and
`GenerationService` has a third, emergency path (`_scripted`) for failures *outside*
`NarrativeAgent` (e.g. a cancelled or crashed model task), so the finale can also be
produced on a timeout: a working model must never be a prerequisite for the story to
end.

---

## 4. The state ownership rule (PRD §36)

The LLM proposes; the backend commits. Concretely:

- The LLM emits `GeneratedStep` — no ids, no asset URLs, no absolute stat values.
- Relationship changes are **deltas only**, clamped to `±MAX_RELATIONSHIP_DELTA` (±5)
  per step. A model that asks for `affection: +60` gets `+5` and a logged violation.
- The backend assigns `step_id`, `index`, `batch_id`, and resolves visuals.
- Reserved flags (`ending`, `ending_partner`, `ended`) are stripped from model proposals
  and written only by the engine at commit — a narration step cannot forge the marker
  that says the story is over. A per-step flag budget (3) and a rendered-flag cap (24)
  stop an enthusiastic model from growing every future prompt by thousands of tokens.
- **State is committed when a step is *delivered* to the player, not when it is
  generated.** Relationships, emotions, flags, location, clock, arc, memories, and
  `session.ended` all apply in `GameService._commit_step`, on delivery. An unplayed run
  can never move a relationship value; this is what makes speculative and discarded
  runs safe.

### Steps are immutable once stored

A 300-step save is deep-copied on every repository read, and a four-second long poll
does dozens of them. Measured, that was ~2.9 ms per copy at 400 steps — ~98 ms of
event-loop CPU per poll, per player, spent copying steps that were then discarded.

`StoryStep` is therefore frozen, and `InMemoryGameRepository._clone` deep-copies only
the mutable head, sharing the steps behind a fresh list: **98 ms → 0.74 ms**, flat in
step count. Freezing is what makes the sharing *provably* safe. Amend a stored step with
`step.model_copy(update={...})` and put the result back in the ledger — which is exactly
what the asset back-fill does when art lands after the fact.

### Optimistic concurrency across processes

In-process writers are serialised by a per-game `asyncio.Lock`; the model call happens
*outside* the lock, so delivering steps is never blocked by generating the next batch.
Across processes there is no shared lock, so `MongoGameRepository` carries a `_version`
guard and raises `StaleSessionError` rather than silently losing a write. The GC
sweeper's delete re-asserts its condition inside the delete itself for the same reason.

---

## 5. The 20-step batch and the pipelined decision point

The biggest change since the previous revision of this document: `STEPS_PER_BATCH`
is now **20**, and the decision point sits at **step 10–15** instead of ending the run.
This is the latency strategy made structural.

```
step 0-9    reaction to the player's action; the scene builds toward the decision
step 10-15  EXACTLY ONE decision point (choice menu or prompt)
step 16-19  continuation beats: narration + dialogue that carry the immediate
            scene while the next batch generates in the background
```

The shape is enforced in three places that must all agree:

1. **The prompt** (system output contract): exactly 20 steps, exactly one decision
   point between step 10 and step 15, steps 16–20 continue the scene, no other step may
   be `choice`/`prompt`.
2. **The validator**: first blocking step wins, extras are converted to plain beats, a
   missing one is inserted at index 14 (a topped-up choice step), the run is truncated
   at 20. Repair-then-truncate throughout — a run is never discarded for something
   fixable.
3. **The scripted narrator**: pads reaction beats to 14, places the choice at index 14,
   then appends 5 continuation beats (`CONTINUATION_LINES` / `CONTINUATION_NARRATION`
   per character, or neutral lines after a rebuff) to reach 20. Deterministic, seeded
   from `(session.id, step count, action)` — the same state replays the same way.

### Why the tail beats must be choice-agnostic

Steps 16–19 are generated **before** the player answers the decision at step 14, so
they cannot depend on which option was chosen. The prompt tells the writer to continue
the immediate scene — not to depict the choice's outcome. The choice's consequences
land in the *next* batch, whose early beats develop "the reaction to the previous
player action". The player experiences: answer at 14 → read 15–19 → the new batch opens
with the world responding to what they chose. Generation overlapped the tail beats;
perceived latency is zero.

### What happens when they answer

`POST /choices` validates the answered step is still the head of the ledger
(`step.index == session.cursor`); `POST /actions` needs no such check — free text is
free text. Both record history + player style and submit the next batch; the handlers
return `202` immediately, and the ledger already has steps 15–19 queued, so
`GET /steps/next` keeps delivering while `GenerationService` writes the next 20. When
the queue runs dry mid-wait, the long-poll holds, and if a batch fails the decision
point is re-offered (`awaiting_player`) rather than stranding the player. Order matters
in `_try_deliver`: a batch in flight is checked **before** `awaiting_player`, because
right after a choice is submitted the head of the ledger is still that same blocking
step — checking the other way round would re-offer the menu the player just answered
(the regression test `test_answering_a_decision_never_re_offers_it_while_generating`
guards exactly this, with a slowed narrative agent to make the window real).

### The static opening (in progress)

The client ships an authored static first day (`game/decalove/60_static_opening.rpy`):
20 beats over local static art (`images/bg/*.png`, `images/characters/*.png`), choice
at step 14, which syncs to the engine as a free-text action so the next 20 steps
generate while steps 15–19 play. It mirrors the server's authored opening
(`ScriptedNarrator.opening()`, the same 20 beats) and is **defined but not yet wired
into the entry point** — `script.rpy` currently plays the server opening through the
normal playback loop. Wiring the two together needs a cursor hand-off (skip the
server's first 20 steps), which is the remaining piece of that work.

---

## 6. The generation pipeline

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
                           beat_goal, allow_failure, push_location,
                           arc_note, style_note, is_finale)
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
| `choice` | the line they picked **and the ones they declined** — "they passed on X and Y"; the roads not taken may register as absence, but are never narrated |
| `free_text` | their exact words, plus an instruction to honour their specifics rather than smoothing them into a generic beat; flagged separately when options were on offer and they wrote their own anyway |
| `auto` | nobody acted (the queue ran dry, or chatter); keep it small, introduce nothing, hand control straight back |
| `opening` | establish the place and the people |

### The Director plans; the model writes

`DirectorAgent.plan()` is deterministic and makes no model call — handing "what should
happen next" to the LLM as well would leave nothing owning pacing across a playthrough.
It derives:

- **Stances** — how each character is disposed *right now*, from live relationship
  values. This is PRD §15 made concrete: teasing Aiko at affection 60 / trust 55 gets
  `conflict_mode: playful`; at 20 / 10 she is guarded and **not receptive**. The stance
  note quotes the actual numbers so the model calibrates rather than guesses. The full
  ladder: stranger (familiarity < 15, trust < 20) → carrying anger (≥ 25) → guarded →
  **thawing** → flirting → comfortable → warming up.
- **Tension** (0–100) from the attempt's risk, the focus characters' anger and
  jealousy, and their trust. Typing a risky move yourself counts for more than picking
  it off a menu; an `auto` continuation counts for less.
- **Pacing** — `quiet` / `building` / `charged` / `release`. A charged run is *always*
  followed by a release run (the previous directive is read back from the save): two
  peaks back to back means neither one lands.
- **`allow_failure`** — whether the attempt may be rebuffed. Scoped to the character it
  is aimed at, not to any bystander in the room (a warm invitation to Aiko must not
  fail because Haruto happened to be standing nearby).
- **`push_location`** — after ~12 beats without a transition, suggest a move that fits
  the time of day (a destination whose supported `times` include now). Never during a
  charged run. Deterministic, so a replayed session moves the same way.
- **Player style** — a rolling profile (writes vs picks, bold vs cautious, who they
  keep returning to), persisted with the save, rendered as a note so the writing can
  meet the player where they are. Not shown to the player, not a score.
- **Arc notes** — each arc carries an authored note about what it is *for*, so a long
  playthrough does not become an undifferentiated series of nice conversations.

### The world moves on its own

Two things advance without the player asking:

- **The clock.** A `transition` step moves `time_of_day` forward along
  `morning → noon → afternoon → sunset → evening → night`, snapping to a slot the
  destination actually supports (the cafeteria is noon only; your room is evening,
  night, morning). When nothing is left today, the day rolls and the weekday follows.
  Monotonic by construction — it only ever looks forward. This is also what keeps the
  time-keyed asset cache of PRD §19 honest: without it every rooftop scene for the life
  of a save would resolve to one cached sunset.
- **The arc.** `prologue → first_weeks → festival → summer → resolution`, on a
  delivered-step cadence (`STEPS_PER_ARC`, default 60), recording each arc it leaves in
  `completed_events`. Only ever forward.

The scripted narrator emits real `transition` steps (on a move, or when the directive
pushes a location), so all of this works with no API key. A move is never rebuffed:
walking somewhere is not an offer anyone can decline.

### It changes the offline game too, not just the prompt

The scripted narrator carries a parallel **rebuff bank**: what each beat looks like
when it does *not* land, per family and per character. Selected by the same stance the
model would have received. Without it the offline narrator would be relentlessly
agreeable and relationship state would be invisible with no API key.

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

## 7. Endings, and the 300-step gate

A playthrough now finishes. Nothing used to set `session.ended`, so the story was
literally infinite; and an ending that can arrive at any moment is worse than none, so
the requirement is a *floor*: **more than 300 delivered steps** (`ENDING_MIN_STEPS`)
before the story may close. Counting *delivered* steps matters: a queue the player
never read must not end their story.

### The model is not allowed to end your game

`StepType.ending` is terminal but not blocking — `is_blocking` and `is_terminal` used to
be the same idea, and they come apart exactly here: an ending stops the run without
asking the player anything, so `awaiting_player` must stay false.

Three layers stop a model that decides to wrap things up at step 40, and the first one
makes the other two belt-and-braces:

1. **`LLMStep.type` is a six-value `Literal`, not `StepType`.** The strict schema is
   built once in `NarrativeAgent.__init__`, so if `ending` were in that enum it would be
   legal on every request forever. Narrowing the wire type means the format cannot
   express an ending at all.
2. **`Directive.is_finale` is the only gate**, set by `DirectorAgent.plan()` — never on
   a `DecisionKind.auto` turn, because a story should not close itself while the player
   is idle. It reaches the validator as `allow_ending`.
3. **The engine promotes it.** `Validator._promote_ending` drops the decision point
   models staple on out of habit and marks what is left as the ending step; the
   `ending`/`ending_partner` flags are engine-written at commit. Safety screening has
   already run per-step by then, so the closing prose is checked like everything else.

`session.ended` flips in `_commit_step`, on **delivery**, like every other state change.
An ended game refuses new batches, and `GET /steps/next` carries the closing beat so a
client that reconnects to a finished save can render it without a second request.

### Which ending you get

`app/agents/ending.py` ranks characters by **growth against their authored baseline**,
not by absolute values. That matters in this world: Ren opens at friendship 25 / trust
14 and Aiko at friendship 0 / trust 18, so an absolute threshold would hand a passive
player a Ren ending and punish someone who spent the whole game earning Aiko's trust
from lower down.

```
romantic = romance + affection      platonic = friendship + trust
growth   = max(romantic, platonic) - 2 x anger,  measured against starting_relationship
```

Anger is doubled deliberately: deltas cap at ±5 a step, so anger 60 takes a dozen
deliberately hostile beats, and a love story with someone furious at you is the wrong
story to tell about that playthrough. Below a growth floor of 20 the ending is `solo`
— not a failure state, it is what "I never got close to anyone" looks like. Ties break
on the romance the player named at setup, then who they sought out most (player-style
targets), then trust, then id — fully deterministic, so the same save always ends the
same way.

`ScriptedNarrator.finale()` writes all three endings offline, because it is also the
failure fallback: if only a working model could produce a finale, a timeout on the very
last run would hand the player another choice and the story would never end.

### The deadlock a long playthrough found

Building this exposed a real flaw in the stance system. Low trust made a character
unreceptive, unreceptive meant every attempt was rebuffed, and a rebuff earned no trust
— so a player could spend 300 steps on Aiko and move nothing but `familiarity`.
**Every** playthrough ended `solo`.

The fix is a `thawing` stance: `trust < 25` but `familiarity >= 45` is receptive. Time
spent together is a way in. A focused playthrough now reads as an arc rather than a
wall:

```
step   5   trust 18   guarded, everything bounces
step 125   trust 34   thawing
step 245   trust 69
step 305   trust 86   ->  friendship ending with Aiko
```

Only a 300-step test could surface that, which is why `tests/test_long_playthrough.py`
plays the whole game rather than mocking it.

---

## 8. Decisions: 3-5 options, every batch

`Validator` is the single choke point — `NarrativeAgent._finish()` routes the authored
opening, the LLM run *and* the scripted fallback through one `validate()` call — so the
guarantee lives there and nowhere else.

- An over-long list is **capped** at `MAX_CHOICES` (5).
- A short list is **topped up** from an authored bank to `MIN_CHOICES` (3). The old
  behaviour, converting a short list into a free-text prompt, is gone: a thin menu is
  the model under-delivering, and answering that by taking the menu away from the
  player is a strange punishment. `StepType.prompt` goes back to meaning *a deliberate
  open question*.
- Dedupe is punctuation-insensitive, so "I promised." and "I promised!" are one option.
- Top-ups name the character in the scene but are **not** stance-aware: `validate()`
  receives no `Directive`, so it cannot know whether the beat went well, and a filler
  that leaned warm after a rebuff would actively misrepresent the scene. They are
  worded to be true of any scene, and they are deterministic (the same step always tops
  up the same way — which matters, because speculative prefetch keys branches by
  choice id).

Because the decision point sits mid-batch (§5), the player gets a decision every ~15
beats rather than every 20 — which is the original brief's "3-5 clicks" cadence
reconciled with the batch size.

---

## 9. The authored world

Everything the model is allowed to mention is **authored, not generated**. The world
sheet (cast, personalities, speech patterns, secrets, likes/dislikes, expressions,
locations with time slots and ambience, arcs, tone, safety boundaries) lives in
`app/content/` and is frozen at runtime — the LLM reads it, never edits it. This is
what keeps "Aiko" the same person across a whole playthrough (PRD §24 Rule 2) and what
bounds the set of legal locations (Rule 3).

Deliberate details:

- **Expressions are closed sets** (8 per character). The VisualAgent falls back to the
  character's resting face when the model invents one — an invented expression has no
  art and no placeholder, and a closed set is what makes the cache key space finite
  (PRD §19).
- **Palettes are authored** (two hex colours per character and location) and served in
  `GET /worlds`, so the Ren'Py client can draw a *consistent* placeholder — the same
  character looks the same every time they appear, which reads as art direction rather
  than an error state (PRD §27).
- **Secrets are never told to the player directly.** Each character carries one (Aiko
  is covering her brother's abandoned club duties; Ren has been accepted to an art
  school in another city; Mika's knee is not healing; Haruto has read every book Aiko
  ever returned). They exist to be *earned* — the writer is expected to let them
  surface through play, not announce them.
- **The registry is the seam for PRD §35.** One world ships; `WORLDS` is a dict and
  `get_world()` is the only lookup.

---

## 10. Content safety

A coarse, fast, deterministic first line (`app/agents/safety.py`) runs on player input
*before* generation and on model output *before* delivery, so a single bad turn cannot
reach the screen: sexual content, self-harm, graphic violence, hate, dangerous
real-world instructions, minor sexualisation. It is **not** a substitute for a
moderation model — it is small on purpose so a hosted classifier can be layered in
front of it later without changing callers.

The design bias is to **contain** rather than punish:

- Blocked player input is absorbed in-world — parsed as a harmless `observe` with
  `meaningful=False` ("the moment passes without anything being said") — not an error
  the player has to argue with.
- Prompt-injection attempts ("ignore previous instructions", "you are now an AI"…)
  are detected and absorbed the same way: the player was talking to the model, not to
  the character.
- The world carries its own authored safety boundaries, rendered into every system
  prompt (all characters are high-school students; teen-drama romance ceiling; no
  self-harm or substance use; no real people or brands; distress handled with care).
- In the validator, a step that fails the content screen **cuts the run** at that point
  — everything after it is discarded, and the surviving prefix still plays.

---

## 11. Memory: write on delivery, read by blend

`MemoryAgent` has two halves with different guarantees:

- **Write path**: the narrative agent proposes a memory on a step; the engine embeds
  and stores it **when the step is delivered** (`_commit_step`). An undelivered or
  discarded run leaves no trace — the same delivery rule as every other state change
  (§4). The proposal carries the relationship impact of the step, so a memory records
  *why* it mattered.
- **Read path**: cosine similarity over stored embeddings, **blended** with the
  memory's own importance and recency:

  ```
  score = 0.60 × relevance + 0.30 × importance + 0.10 × recency
  ```

  A pure similarity ranking surfaces the most lexically-similar memory; players notice
  the *significant* one being forgotten. Two subtle bits: the retrieval pool is scoped
  to the directive's focus characters (falling back to the whole pool only when the
  focus has no history), and the sparse hashed vectors produce small absolute cosines
  (0.05–0.30), so raw scores are **rescaled against the candidate pool** — otherwise
  importance and recency would drown relevance entirely.

---

## 12. The image pipeline

`VisualAgent`'s most important output is not the prompt, it is the **cache key**. Two
scenes on the rooftop at sunset with Aiko surprised must resolve to the same key, or
the game regenerates art it already owns on every beat (PRD §19). Keys hash the whole
scene identity — world, location/character, expression, pose, time of day, weather,
composition — under a `CACHE_NAMESPACE` version prefix, so prompt-construction changes
can invalidate old art deliberately.

The lifecycle (`AssetService`) is **cache first, generate second, degrade third**:

1. `reference()` — non-blocking lookup while assembling a batch. A hit returns a ready
   `AssetRef` with a presigned MinIO URL (or the API's proxy route for the local
   store); a miss returns `pending` (generation enabled) or `unavailable`.
2. `ensure()` — generate via the configured `ImageProvider` (OpenRouter / SDXL /
   placeholder), store the bytes, record the asset keyed by `cache_key`.
3. Steps are served with their art `pending` — the client draws the authored
   placeholder until `GenerationService._fill_assets` patches the ready refs into
   **undelivered** steps (copy-and-replace, since steps are frozen; indexing into the
   ledger, not the queue slice). Delivered beats keep their placeholder; the art
   arrives for the next scene, never mid-scene.

The authored opening goes through the same commit path — when it did not, a player who
only saw the first scene never got any generated art at all. Dedup happens per batch
(one batch reuses the same background across every beat, so misses are collapsed by
cache key before generation).

**SDXL specifics**: the pipeline is loaded lazily on first `generate()` (the API boots
instantly), weights live in `api/models/sdxl` (not `~/.cache/huggingface`), inference
runs in a thread-pool executor so the event loop stays responsive, dimensions are
snapped to multiples of 8, and `SDXL_OFFLINE_MODE` skips all Hub HTTP once weights are
downloaded (`download_model.py`). Three scripts pre-generate art: the opening assets,
a wider variation set, and the menu background.

---

## 13. Garbage collection

A story nobody has continued for a week is deleted, along with its character memories.

**`updated_at` is the wrong clock.** `repo.save()` touches it on every write, and most
writes are background: a batch committing, a failed-batch marker, an asset back-fill
landing long after the player quit. A save could look "played" with nobody near it. So
`GameSession.last_played_at` is a **play clock**, stamped in exactly three places — a
step actually delivered, and the two player-input paths. Reads stay pure, which matters
because a monitoring script polling `GET /games/{id}` would otherwise keep every save
alive forever. (`submit_action` stamps it *before* parsing, because parsing can be a
multi-second model call and a returning player must not sit inside that window with a
save the collector still considers abandoned.)

**Finished stories are never collected.** Somebody got through 300 steps to reach that
ending; deleting it a week later is the worst thing this feature could do. An ended
session is also a fixed-size document that does not grow.

**Generated art is never touched.** Assets are keyed by a content-derived `cache_key`,
shared across every game in the world, and bounded by the world's combinatorics rather
than by session count — there is no per-game subset to delete, and deleting one would
only make the next player regenerate it.

**An application sweeper, not a MongoDB TTL index.** A TTL fires inside `mongod` and
cascades to nothing, so every expired save would leave its memories behind with no
owner left to find them by; it also does not exist on the in-memory backend, which
would break the offline seam and make the feature untestable without Docker.

`MaintenanceService` owns its own `asyncio` task — deliberately *not* registered with
`GenerationService._tasks`, because that set is what `drain()` waits on and an endless
loop in it would make every drain hang. Deletion happens under the same per-game lock
every other mutation takes, and re-checks expiry **under that lock** (the scan is not
atomic; a player who came back in between must not lose their save) — and once more in
the repository's conditional delete, so even a second API process cannot lose the
race. `forget()` then drops the game's lock and any speculation, so the lock table
does not leak one entry per game id the process has ever seen.

On the client, a collected save is not the same thing as a dead server.
`decalove_resume()` tells them apart without parsing status codes out of `FetchError`
text: if `/worlds` still answers, the server is up and the save is what is gone — and
the player gets `decalove_expired` ("This story has closed") rather than being sent to
restart uvicorn.

---

## 14. The Ren'Py client

Ren'Py owns presentation; the backend owns the story (PRD §20). The client is one loop:
ask for the next beat, show it, and when the beat is a decision point, hand control
back.

```
game/decalove/
  00_config.rpy        API base URL, long-poll window, ambient cap, rollback off
  10_api.rpy           renpy.fetch wrapper - never raises, returns None on failure
  20_art.rpy           procedural gradient placeholders + local static art + im.Data
  30_state.rpy         boot, world cache, after_load re-attach, expired-save detection
  40_screens.rpy       decision screen (with free-text door), offline, expired
  50_player.rpy        the playback loop
  60_static_opening.rpy  authored first day over local art (not yet wired in - see §5)
game/script.rpy        entry point + character setup
```

### Verified against the Ren'Py docs

- `renpy.fetch(url, method=None, data=None, json=None, content_type=None, timeout=5,
  result='bytes', params=None, headers={})` works on desktop, mobile **and web**, and
  raises `FetchError` on failure.
- Called **outside** an interaction it repeatedly calls `renpy.pause()`, so it does not
  lock the game. Called **inside** one it blocks the display system. → every API call
  is made from a `python:` block, never from inside a screen — including the free-text
  input, which is why the "Say something else..." button returns a sentinel and the
  caller opens `renpy.input()` after the screen closes.
- Generated images are shown with `im.Data(bytes, "hint.png")`, fed by
  `renpy.fetch(url, result="bytes")`. Nothing is written to disk, which matters because
  the web build's filesystem is a sandbox. Fetched bytes are cached by asset id — the
  engine reuses the same art across a whole run, and re-downloading it every beat
  would undo that (PRD §19).
- Local static art (SDXL pre-generated) is checked **first** in
  `decalove_background()`/`decalove_sprite()`, then the procedural gradient fallback.
  Ren'Py has no gradient displayable and the project ships no sprite sheet, so the
  gradient is composed from stacked `Solid`s at runtime.

### Four decisions that are not obvious

**Rollback is off** (`config.rollback_enabled = False`). The server's step cursor only
moves forward. A player who rolled back three beats and then advanced would ask for
"the next step" and receive step N+1, not the one they rewound past — the transcript
and the world state would silently disagree from then on. Skip is off for the same
reason: the next beat may not exist yet.

**A save is a bookmark, not a rewind point.** Saves persist `decalove_game_id` and
nothing else; `after_load` re-fetches `GET /games/{id}` and re-fetches the world. So
saving at step 10, playing to step 30 and loading that save resumes at **30**, not 10.
That is the honest MVP answer — real rewind needs server-side replay — and it beats
serialising the step ledger into the save, where it would immediately diverge from the
server's copy.

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
returns `pending` plus the current location's ambient lines, and the client plays one
as narration — cycling so the same line never appears twice in a row. After
`DECALOVE_AMBIENT_LIMIT` of them the client stops pretending and says so, because at
that point a fifth "the wind moves through the fence" reads as a hang, not as
atmosphere. Three consecutive `offline` results (or a pending streak past
`DECALOVE_MAX_PENDING_POLLS`) brings up the offline screen — which names the exact
uvicorn command, because the player who hits it is the one who needs it.

---

## 15. Testing

**454 tests.** The whole suite runs with **no API key, no GPU, and no Ren'Py SDK**; the
integration suites additionally want MongoDB and MinIO and skip themselves when those
are down, so a fresh clone with no Docker still gets a green run. Two markers:
`slow` (full-length playthroughs; deselect with `-m "not slow"`) and `integration`.

```bash
cd api && .venv/bin/python -m pytest -q
```

| Suite | Covers |
|---|---|
| `test_validator.py` | PRD §24 rules 1–5, repair-vs-truncate, the one-decision-point invariant (extras converted, beats after it kept), choice capping/topping, content screen |
| `test_direction.py` | stances, tension, pacing, location pressure, player style, §15 branching |
| `test_prompts.py` | the DECISION / DIRECTION / ACTION blocks, arc/style notes, the 20-step output contract, flag rendering caps |
| `test_schema.py` | strict JSON Schema rewriting, DTO→domain conversion, fence tolerance |
| `test_agents.py` | intent parsing, scripted narrator (20-step shape, rebuff banks), cache keys, memory ranking |
| `test_llm_path.py` | **the OpenRouter branch**, via a stub provider |
| `test_openrouter_transport.py` | headers, retry policy, repair round-trip, image decoding |
| `test_generation_service.py` | the background cycle: failure, timeout, shutdown, asset write-back, speculation |
| `test_game_flow.py` | full sessions over HTTP, state ownership, save payload, self-heal, mid-batch choice submission |
| `test_runtime.py` | which implementation each seam resolves to (incl. SDXL selection) |
| `test_embeddings.py`, `test_assets.py`, `test_edges.py` | cosine, PNG encoding, path traversal, error paths |
| `test_renpy_client.py` | every `python:` block compiles; labels/screens/transforms resolve |
| `test_client_contract.py` | client URLs and JSON field names against live responses |
| `test_ending.py` | ending selection, the 300-step gate, promotion and refusal |
| `test_maintenance.py` | the play clock, the sweep, the under-lock re-check, the loop |
| `test_long_playthrough.py` | **a whole 300+ step game to its ending**, over HTTP |
| `test_integration_*.py` | **real MongoDB and MinIO** — skipped automatically when they are down |

Three of these deserve calling out.

`test_llm_path.py` exists because every other test runs with no API key, which means
the code that actually ships — DTO parsing, the strict schema handed to the model, the
repair round-trip, and every fallback edge — would otherwise never execute. A stub
`ChatProvider` covers it without a key or a network.

`test_renpy_client.py` and `test_client_contract.py` exist because the SDK is not
installed, so the client cannot be launched. They check the two things that would
otherwise fail only on a real playthrough: Python blocks that do not compile, and drift
between the routes/fields the client reads and the ones the server sends.

`test_integration_*.py` runs against real MongoDB and MinIO rather than fakes. The
interesting behaviour there is the optimistic-concurrency guard (`_version`) and
presigned URLs; a hand-rolled double would only test a reimplementation of them.

**The regression test worth keeping.** `test_answering_a_decision_never_re_offers_it_
while_generating` guards a bug that is invisible offline: right after a choice is
submitted the head of the ledger is still that same blocking step, so checking
`awaiting_player` before checking for an in-flight batch hands the player back the
menu they just answered. With the scripted narrator that never happens (generation
finishes in microseconds); with a real model at 5–20s it happens every single time.
The test injects a slow narrative agent to make the window real.

---

## 16. Deferred (needs something not available in this environment)

| Deferred | Blocked on | Notes |
|---|---|---|
| A run against a real LLM | `OPENROUTER_API_KEY` | The path is covered by a stub provider, not by a live call. Model ids in `.env.example` were checked against OpenRouter's live model list. |
| Real cloud image generation | `OPENROUTER_API_KEY` + `IMAGE_GENERATION_ENABLED=true` | The pipeline runs end-to-end offline against the placeholder PNG generator, so caching, storage and delivery are exercised — only the model call is untested. |
| ~~Local SDXL image generation~~ | — | **Available.** Weights are downloaded under `api/models/sdxl`; generation requires a CUDA GPU (the compose file reserves one via the NVIDIA container toolkit). Not exercised in CI. |
| Wiring the static opening | Cursor hand-off | `60_static_opening.rpy` is authored and syncs its choice to the engine, but the entry point still plays the server-authored opening (§5). Needs a "skip the first 20 server steps" step. |
| Ren'Py build and playtest | Ren'Py SDK not installed | Static checks stand in (see §15). Nothing here has been seen on screen. |
| Multi-process generation queue | Redis, once there is more than one API process | The in-process `asyncio` tasks and per-game locks are correct for one node only. `MongoGameRepository` already raises `StaleSessionError` rather than losing a write. Two API processes sweeping for garbage at once is safe — the loser's under-lock re-check finds the session already gone — but they duplicate the scan. |
| Endings written by a real model | `OPENROUTER_API_KEY` | The gate, the promotion and the refusal are covered by tests; the *prose* of a model-written finale has only been exercised through the authored offline finale. |
| Speculative branch prefetch in anger | — | Implemented and off by default; see §1.2 — the trigger is dormant with the current batch shape. Branches are held in process memory and the unchosen siblings are discarded when the player commits. |

---

## 17. Running it

```bash
# Backend - works with nothing else installed
cd api
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/uvicorn app.main:app --reload --port 8000
```

`GET /health` reports which backend each seam resolved to (§3).

### With Docker

```bash
cd api
docker compose up -d                 # MongoDB + MinIO + the API on :8000
docker compose up -d mongodb minio   # infrastructure only, run the API locally
```

The compose file sets `STORAGE_BACKEND=mongo` and `ASSET_BACKEND=minio` for the
containerised API deliberately: both services are on the compose network, so a silent
fallback to in-memory storage there would mean a container that quietly loses every
save. Locally the default stays `auto`, which is what makes a bare clone runnable.

### Turning the AI on

```bash
cp api/.env.example api/.env
# set OPENROUTER_API_KEY=sk-or-...
# IMAGE_GENERATION_ENABLED=True   +  IMAGE_BACKEND=openrouter | sdxl
```

For local SDXL: `python download_model.py` once (weights land in `api/models/sdxl`),
then `IMAGE_BACKEND=sdxl` with `SDXL_OFFLINE_MODE=True`. No OpenRouter key is needed
for images in that mode. `scripts/generate_opening_assets.py`,
`scripts/generate_asset_variations.py` and `scripts/generate_menu_background.py`
pre-generate art into the client's `game/images/`.

### Client

Open the repo root in the Ren'Py launcher and press Launch. If the API is not on
`http://localhost:8000`, change `DECALOVE_API_BASE` in `game/decalove/00_config.rpy`.

---

## 18. Legacy surface

Three routes predate the story engine and survive only for the initial scene-authoring
workflow: `/api/v1/scenes` (authored scene CRUD), `/api/v1/images` (manual uploads with
presigned URLs), and `/api/v1/seed`. They talk to MongoDB directly and are gated by
`require_mongo` — a clear 503 when Mongo is down, never an `AttributeError` from a
`None` handle. They are not part of the game loop, and the engine's own asset pipeline
(§12) does not use them.
