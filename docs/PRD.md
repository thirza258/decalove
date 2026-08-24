# PRD — Decalove: AI Agent Visual Novel Game

> Source of truth for product scope. Captured verbatim from the original product brief.
> Engineering decisions that *interpret* or *deviate from* this document live in
> [`ARCHITECTURE.md`](./ARCHITECTURE.md) — including two internal contradictions in
> sections 10/24 and 14/15 that had to be resolved before implementation.

## 1. Product Overview

**Decalove** is a web-based, AI-powered visual novel game built with **Ren'Py**, where the player interacts with an evolving story through natural-language input and traditional visual-novel choices.

Unlike a conventional visual novel with a fixed branching tree, Decalove uses an **AI Agent Story Engine** to dynamically generate the next portion of the story based on:

* Player input
* Previous story events
* Character relationships
* Character personalities
* Current emotional state
* World state
* Previous decisions
* Story objectives
* Generated visual assets

The system generates approximately **10 story steps ahead** whenever the player provides meaningful input. These steps are progressively revealed through the visual-novel interface, hiding the generation process from the player.

The goal is to make the game feel like a traditional handcrafted visual novel while providing the adaptability of an AI-driven RPG.

---

# 2. Product Vision

> **"A visual novel where the story is written for you, not just played by you."**

Decalove combines:

**Visual Novel + AI Agent + LLM + Image Generation + Player Choice + Dynamic Storytelling**

The player should feel that:

> "The game understands what I want to do and turns my decision into a real story."

The AI should not feel like a chatbot. It should operate behind the scenes as the game's **director, writer, narrator, and world simulator**.

---

# 3. Goals

### Primary Goals

1. Create a web-based visual novel experience.
2. Allow players to influence the story using natural language.
3. Dynamically generate story progression using an LLM.
4. Generate character/background imagery using an image-generation model through OpenRouter.
5. Maintain persistent character relationships and world state.
6. Pre-generate approximately 10 story steps after meaningful player input.
7. Hide AI generation latency behind normal visual-novel gameplay.
8. Make generated content feel coherent rather than random.
9. Support branching narratives without requiring developers to manually define every branch.

### Secondary Goals

* Allow replayability.
* Allow players to pursue different relationships.
* Support romance, friendship, mystery, comedy, drama, etc.
* Allow AI-generated side events.
* Eventually support multiple story worlds.
* Eventually support player-created characters.

---

# 4. Non-Goals

The initial version will **not** attempt to:

* Generate an entirely new game engine dynamically.
* Generate arbitrary gameplay mechanics.
* Allow unrestricted image generation without moderation.
* Generate unlimited story content synchronously.
* Replace Ren'Py's dialogue/scene system entirely.
* Allow the LLM to directly execute arbitrary code.
* Allow the LLM to control server infrastructure.

The AI operates through a controlled **Game State API**.

---

# 5. Target Platform

### Primary

Web browser.

### Game Runtime

Ren'Py Web / HTML5-compatible deployment.

### Backend

Suggested architecture:

* Python
* FastAPI
* PostgreSQL
* Redis
* Background workers
* OpenRouter API
* Image-generation model
* LLM
* Object storage/CDN

---

# 6. Core Gameplay Loop

The fundamental loop is:

```text
Player enters game
        v
Game loads current world state
        v
Visual Novel presents scene
        v
Player reads dialogue
        v
Player chooses an option
        OR
Player enters natural-language action
        v
AI Agent interprets player intent
        v
Story Agent generates next ~10 steps
        v
State Agent updates world state
        v
Image Agent generates required visuals
        v
Content is queued/cached
        v
Ren'Py continues playing generated scenes
        v
Player eventually reaches generated content boundary
        v
Next generation cycle starts
```

The critical design principle is:

> **AI generation happens ahead of the player's visible progress whenever possible.**

---

# 7. Player Experience

## 7.1 Starting a Game

The player selects:

* New Game
* Continue
* Story/World
* Character preferences
* Optional romance preferences
* Optional story tone

Example:

```text
Choose your story:

[ ] High School Romance
[ ] Fantasy Adventure
[ ] Cyberpunk Mystery
[ ] Supernatural Romance
[ ] Slice of Life
```

For the MVP, Decalove should focus on **one primary story universe** rather than attempting to support unlimited genres.

---

# 8. Story Interaction

The player can interact using two methods.

## Method A — Traditional Choices

Example:

> Aiko looks at you nervously.

> "Are you really going to the festival tomorrow?"

Choices:

```text
1. "Of course. I wouldn't miss it."
2. "Maybe. Why?"
3. "Only if you're going."
```

## Method B — Natural Language

The player can type:

```text
"I tell Aiko that I'll go if she promises to stay with me."
```

The AI interprets the intent and converts it into a valid story action.

The player does **not** directly control the narrative outcome.

For example:

```text
Player Intent:
invite_character

Target:
Aiko

Emotion:
affectionate

Risk:
medium
```

The Story Agent then determines what actually happens.

---

# 9. AI Agent Architecture

Decalove should use multiple logical AI agents rather than one giant prompt.

## 9.1 Director Agent

Responsible for:

* Understanding player intent
* Determining narrative direction
* Maintaining pacing
* Selecting which characters participate
* Determining important events
* Creating the next story segment

---

## 9.2 Character Agent

Responsible for:

* Character personality
* Character memory
* Emotional state
* Relationship state
* Character reactions

Example:

```json
{
  "character": "Aiko",
  "affection": 72,
  "trust": 61,
  "anger": 4,
  "fear": 12,
  "current_emotion": "embarrassed"
}
```

---

## 9.3 World State Agent

Maintains:

* Current location
* Time
* Date
* Active events
* Completed events
* Inventory
* Relationships
* Flags
* Story arcs

---

## 9.4 Narrative Agent

Generates:

* Narration
* Dialogue
* Scene transitions
* Player choices
* Consequences
* Story events

The output must be structured rather than raw prose.

---

## 9.5 Visual Agent

Determines:

* Which image is required
* Character expressions
* Character poses
* Background
* Scene composition
* Image-generation prompt

It then calls the image-generation service through OpenRouter.

---

## 9.6 Validation Agent

Validates generated content before it reaches the player.

Checks:

* Character consistency
* Story continuity
* Invalid actions
* Contradictions
* Forbidden content
* Invalid locations
* Broken state transitions
* Schema validity

---

# 10. Ten-Step Generation System

This is one of the core mechanics of Decalove.

When the player submits an important action:

```text
Player:
"I ask Aiko if she wants to walk home together."
```

The backend does **not** generate only one response.

Instead:

```text
Generate:

Step 1
Step 2
Step 3
Step 4
Step 5
Step 6
Step 7
Step 8
Step 9
Step 10
```

Example:

```text
1. Aiko becomes surprised.
2. She asks whether the player is serious.
3. Player confirms.
4. Aiko agrees.
5. They leave school.
6. They discuss the festival.
7. Aiko reveals something personal.
8. Player responds.
9. Their relationship improves.
10. They reach the train station.
```

The player only sees:

```text
Step 1
v
Step 2
v
Step 3
...
```

The remaining generated steps are stored in a queue.

---

# 11. Hidden Generation

The AI generation process should be invisible.

The player should never see:

```text
Generating story...
Calling LLM...
Generating image...
Updating vector database...
```

Instead, the game continues playing cached content.

Conceptually:

```text
VISIBLE

Scene 1
Scene 2
Scene 3
Scene 4
Scene 5

        v

BACKGROUND

AI generating Scene 6-15
```

This creates the illusion that the story was already written.

---

# 12. Generation Pipeline

```text
Player Input
     v
Intent Parser
     v
Current Game State
     v
Character Memories
     v
Relevant Story Memories
     v
Director Agent
     v
Narrative Planner
     v
10 Story Steps
     v
Validation
     v
Image Requirements
     v
Image Generation
     v
Asset Storage
     v
Story Queue
     v
Ren'Py Runtime
```

---

# 13. Story Step Schema

Every generated step should follow a strict schema.

Example:

```json
{
  "step_id": "story_00123",
  "type": "dialogue",
  "location": "school_rooftop",
  "characters": ["aiko"],
  "narration": "The wind gently moves through the rooftop fence.",
  "dialogue": {
    "speaker": "aiko",
    "text": "You really came..."
  },
  "emotion": {
    "aiko": "surprised"
  },
  "relationship_changes": {
    "aiko": {
      "affection": 3,
      "trust": 1
    }
  },
  "next_choices": [
    {
      "id": "choice_1",
      "text": "I promised I would."
    },
    {
      "id": "choice_2",
      "text": "You sounded like you needed someone."
    }
  ],
  "visual": {
    "background": "school_rooftop_sunset",
    "character": "aiko",
    "expression": "surprised"
  }
}
```

---

# 14. Story Queue

The backend maintains a story queue.

Example:

```text
Game Session

Current:
step_102

Queue:

step_103
step_104
step_105
step_106
step_107
step_108
step_109
step_110
step_111
step_112
```

When the player reaches:

```text
step_108
```

the backend can start generating another batch.

```text
Generate:

step_113 -> step_122
```

This creates a rolling narrative buffer.

---

# 15. Dynamic Branching

The story should not be represented as a traditional static tree.

Instead, it uses a **state graph**.

```text
                +-- Romance
                |
Player - Event -+-- Conflict
                |
                +-- Mystery
```

The same event can lead to different states depending on:

* Player choices
* Character relationships
* Previous actions
* Character personalities
* Story flags

Example:

```text
Player insults Aiko

Aiko affection = 60
-> playful argument

Aiko affection = 20
-> serious conflict
```

Therefore, the same player input can produce different results.

---

# 16. Character Relationship System

Each major character should have relationship attributes.

Example:

```text
Affection
Trust
Respect
Fear
Jealousy
Friendship
Romance
Familiarity
```

These values influence the AI.

Example:

```text
Aiko

Affection: 72
Trust: 81
Respect: 64
Jealousy: 31
Romance: 68
```

The values should not necessarily be directly shown to the player.

---

# 17. Character Memory

Characters should remember important player actions.

Example:

```text
Memory:

Player defended Aiko during school conflict.

Importance:
0.92

Emotion:
gratitude

Relationship impact:
+8 trust
+5 affection
```

The system should use semantic retrieval to find relevant memories when generating new content.

Potential implementation:

```text
PostgreSQL
+
pgvector
```

or a dedicated vector database.

---

# 18. Image Generation

Images are generated dynamically through OpenRouter-compatible image generation APIs.

The Image Agent creates structured prompts based on the current scene.

Example:

```text
Character:
Aiko

Expression:
embarrassed

Pose:
holding school bag

Location:
school rooftop

Time:
sunset

Mood:
romantic

Style:
anime visual novel
```

The generated asset is stored and associated with the story step.

---

# 19. Image Reuse

The system should avoid generating duplicate images unnecessarily.

Before requesting a new image:

```text
Search existing asset cache
        v
Similar scene found?
   v             v
 YES             NO
 v                v
Reuse          Generate
```

Assets can be keyed by:

```text
character
expression
pose
location
time
weather
composition
```

---

# 20. Visual Novel Presentation

The Ren'Py frontend should remain responsible for:

* Dialogue box
* Character sprites
* Backgrounds
* Transitions
* Music
* Sound effects
* Choice UI
* Save/load
* Scene progression

The AI backend should provide content.

This separation is important.

```text
Ren'Py
  v
Game API
  v
AI Story Engine
```

The AI should not directly manipulate the Ren'Py runtime.

---

# 21. Backend Architecture

Suggested architecture:

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
             +------------+------------+
             v            v            v
        Game State     AI Agent     Asset API
             |            |            |
             v            v            v
        PostgreSQL     OpenRouter    Object Store
             |
             v
          pgvector
```

Background workers:

```text
FastAPI
   v
Redis Queue
   v
AI Worker
   +-- Story Generation
   +-- Validation
   +-- Image Generation
```

---

# 22. API Design

### Create Game

```http
POST /api/games
```

### Get Game State

```http
GET /api/games/{game_id}
```

### Submit Player Action

```http
POST /api/games/{game_id}/actions
```

Request:

```json
{
  "input": "I ask Aiko if she wants to walk home with me."
}
```

### Get Next Story Step

```http
GET /api/games/{game_id}/steps/next
```

### Submit Choice

```http
POST /api/games/{game_id}/choices
```

### Get Asset

```http
GET /api/assets/{asset_id}
```

---

# 23. AI Generation Request

The backend should provide the LLM with structured context.

```text
SYSTEM

You are the narrative director of Decalove.

Maintain story continuity.

Never contradict established facts.

Respect character personalities.

Never directly control the player's decisions.

Generate approximately 10 sequential story steps.

...

CURRENT WORLD STATE

...

CHARACTER STATES

...

RELEVANT MEMORIES

...

PREVIOUS EVENTS

...

PLAYER ACTION

...
```

The LLM must return structured JSON.

---

# 24. Agent Rules

The AI must follow several hard constraints.

### Rule 1 — Player Agency

The AI must never force the player to perform an action unless the action was already explicitly chosen.

Bad:

```text
You kiss Aiko.
```

Better:

```text
Aiko moves closer, waiting to see what you will do.
```

---

### Rule 2 — Character Consistency

A character's behavior must match their personality and current emotional state.

---

### Rule 3 — World Consistency

If the player is at school, the AI should not suddenly place them at home unless a transition occurs.

---

### Rule 4 — State Consistency

The AI cannot arbitrarily modify persistent values.

For example:

```text
affection: 40 -> 100
```

without an appropriate event.

---

### Rule 5 — Narrative Continuity

Each generated step must logically follow the previous step.

---

# 25. Generation Latency Strategy

LLM generation and image generation may be slow.

Therefore Decalove should use:

### Pre-generation

Generate the next 10 steps before they are needed.

### Parallel processing

Story generation and image generation should run concurrently where possible.

### Asset caching

Never regenerate an existing asset unnecessarily.

### Streaming

The backend can stream generated steps to the client while later steps continue generating.

Example:

```text
Step 1 ready
v
send to Ren'Py

Step 2 ready
v
send to Ren'Py

Step 3 ready
v
send to Ren'Py

Meanwhile:

Step 4-10 generating
```

---

# 26. Failure Handling

If AI generation fails:

```text
LLM unavailable
        v
Use fallback narrative
        v
Continue game
```

If image generation fails:

```text
Image unavailable
        v
Use existing character sprite
        +
existing background
```

The game should never become completely unplayable because an AI request failed.

---

# 27. Save System

A save should contain:

```text
Game ID
Story ID
Current Step
World State
Character States
Relationship Values
Important Memories
Story Flags
Inventory
Generated Asset IDs
Story Queue
```

Example:

```json
{
  "current_step": 103,
  "story_arc": "festival",
  "character_states": {},
  "relationships": {},
  "memories": [],
  "flags": {},
  "queue": [
    "104",
    "105",
    "106"
  ]
}
```

---

# 28. Content Safety

Because the system dynamically generates content, safety must exist at multiple layers.

```text
Player Input
      v
Input Moderation
      v
LLM Generation
      v
Output Validation
      v
Image Moderation
      v
Game
```

The system should enforce:

* Age-appropriate character definitions
* No disallowed sexual content
* No graphic violence beyond configured rating
* No hateful content
* No dangerous real-world instructions
* No real-person impersonation
* Consistent fictional character boundaries

---

# 29. MVP Scope

The first playable version should be intentionally limited.

### MVP Story

One world:

**High School Romance / Slice of Life**

### Characters

3-5 major characters.

Example:

```text
Aiko
Ren
Mika
Haruto
```

### Locations

5-8 locations:

```text
Classroom
Rooftop
Library
School Gate
Cafeteria
Park
Train Station
Player's Home
```

### Features

* New game
* Continue game
* Traditional choices
* Natural-language input
* AI-generated story
* 10-step generation queue
* Character relationship system
* Character memory
* Dynamic dialogue
* Dynamic scene generation
* AI-generated images
* Save/load

---

# 30. MVP User Flow

```text
Landing Page
     v
New Game
     v
Character Setup
     v
Opening Scene
     v
Dialogue
     v
Choice / Natural Language
     v
AI generates 10 steps
     v
Story begins playing
     v
Player reaches step 7
     v
Next 10 steps generated
     v
Continue
```

---

# 31. Success Metrics

### Engagement

* Average session duration
* Average number of story steps/session
* Number of player interactions
* Returning players
* Stories completed

### AI Quality

* Story continuation acceptance rate
* Player regeneration rate
* Contradiction rate
* Invalid generation rate
* Character consistency score

### Performance

Target:

```text
Initial story generation:
< 10 seconds preferred

Background generation:
< 20 seconds preferred

Normal story-step retrieval:
< 500 ms
```

Image generation should happen asynchronously and should not block already-generated dialogue whenever possible.

---

# 32. Future Features

### Multiplayer Stories

Multiple players influence the same AI-generated world.

### AI Companions

Characters can remember hundreds of interactions.

### User-Generated Characters

Players define:

```text
Name
Personality
Appearance
Background
Relationship preferences
```

### Custom Worlds

Players can create:

```text
Fantasy
Cyberpunk
Horror
Romance
Sci-Fi
Mystery
```

### Voice Acting

Generated dialogue can be converted into speech.

### Music Generation

Dynamic music based on:

```text
Emotion
Location
Story tension
Relationship state
```

### Long-Term Story Arcs

The AI Director can maintain:

```text
Chapter 1
    v
Chapter 2
    v
Chapter 3
    v
Major Arc
    v
Ending
```

---

# 33. Technical Principle

The most important architectural principle is:

> **The LLM generates the narrative, but the game engine owns the state.**

Do not allow the LLM to become the source of truth.

Instead:

```text
PostgreSQL
      v
Source of Truth
      v
AI receives state
      v
AI proposes changes
      v
Validator checks changes
      v
Backend commits changes
```

This prevents the AI from accidentally changing the game's rules.

---

# 34. Core Decalove Architecture

The final conceptual architecture is:

```text
                        DECALOVE
                           |
             +-------------+-------------+
             |                           |
        REN'PY CLIENT              GAME BACKEND
             |                           |
       Visual Novel UI              Game State
             |                           |
             |                  +--------+--------+
             |                  |                 |
             |              AI DIRECTOR      MEMORY SYSTEM
             |                  |                 |
             |           +------+------+          |
             |           |      |      |          |
             |        Story   Character World     Vector
             |        Agent    Agent    Agent     Memory
             |           |      |      |          |
             |           +------+------+          |
             |                  |                 |
             |             10-Step Plan           |
             |                  |                 |
             |             Validator              |
             |                  |                 |
             |           +------+------+          |
             |           |             |          |
             |       Dialogue       Visual Agent  |
             |                         |          |
             |                    Image Generation|
             |                         |          |
             +-------------------------+----------+
```

---

# 35. Product Differentiator

Traditional visual novels:

```text
Developer-written
       v
Fixed branches
       v
Limited outcomes
```

Decalove:

```text
Player intent
       v
AI Director
       v
Character simulation
       v
World simulation
       v
10-step narrative generation
       v
Dynamic visuals
       v
Player experiences unique story
```

The key experience is not simply **"AI writes dialogue."**

It is:

> **An AI agent continuously directs a visual novel around the player's actions while the player experiences it as a seamless, pre-rendered narrative.**

This distinction should define the product architecture and gameplay design.
