"""Prompt construction — PRD §23.

One system prompt carrying the world and the hard rules, one user message carrying the
mutable state. Keeping them apart is what makes prompt caching worthwhile later: the
system half is identical for every call in a world.
"""

from __future__ import annotations

from app.content.world import World
from app.domain.direction import DecisionContext, Directive
from app.domain.intent import PlayerIntent
from app.domain.memory import MemoryRecord
from app.domain.state import GameSession
from app.domain.story import StoryStep

#: Upper bound on how many world flags are rendered into the prompt.
MAX_RENDERED_FLAGS = 24

_RULES = """HARD RULES (violating any of these invalidates the whole response)

1. PLAYER AGENCY. Never narrate a decision, speech, or deliberate action by the player.
   You may describe what happens *to* them and what others do in front of them.
   Bad:  "You kiss Aiko."   /   "You agree, and tell her you'll be there."
   Good: "Aiko moves closer, waiting to see what you will do."
   Never write dialogue with speaker "player".

2. CHARACTER CONSISTENCY. Behaviour must follow the cast sheet and the character's
   current emotional and relationship state. A character with low trust does not suddenly
   confide. Characters do not know things they have not been told.

3. WORLD CONSISTENCY. Only the listed location ids exist. The scene stays in the current
   location unless you emit a step of type "transition" that moves it; after that step,
   later steps use the new location.

4. STATE CONSISTENCY. relationship_changes are small deltas, never absolute values, and
   never larger than {max_delta} on any axis in a single step. Big feelings are earned
   across several steps, not asserted in one.

5. CONTINUITY. Every step follows from the one before it and from the established facts.
   Never contradict anything in the history or the memories.

OUTPUT CONTRACT

* Return exactly {max_steps} steps.
* Place exactly ONE decision point (a step of type "choice" with {min_choices}-{max_choices}
  options, or type "prompt") between step 10 and step 15 of this batch (i.e. at the 10th
  to 15th step of the {max_steps} steps).
* Steps before the choice develop the reaction to the previous player action and build the scene.
* The choice step offers the player meaningful options for where to take the story next.
* Steps after the choice step (e.g. steps 16 to {max_steps}) MUST be narration and dialogue
  that naturally continue the immediate scene forward while the next run generates in the background.
* No other step in the run before step 10 or after step 15 may be "choice" or "prompt".
* Choice option text is what the PLAYER would say or do - written in their voice, short,
  and genuinely different from one another in intent, not in wording. Fewer than
  {min_choices} real options is worse than none: if you cannot find {min_choices}
  distinct intentions, use type "prompt" and let them write their own.
* Every step needs a `visual`. `background` must be a location id from the list.
  `expression` must come from that character's expression list.
* Use `memory` sparingly: only for things a character would still be thinking about a
  week later. importance 0.0-1.0.
* narration is prose, 1-3 sentences, present tense, close third person about the world.
* Write dialogue that sounds like the specific character, not like a generic anime script.

CONTENT BOUNDARIES ({rating})
{safety}"""


def build_system_prompt(
    world: World,
    *,
    max_steps: int,
    max_delta: int,
    rating: str,
    min_steps: int = 3,
    min_choices: int = 3,
    max_choices: int = 5,
) -> str:
    cast = "\n".join(f"  - {character.brief()}" for character in world.characters)
    expressions = "\n".join(
        f"  - {character.id}: {', '.join(character.expressions)}" for character in world.characters
    )
    locations = "\n".join(f"  - {location.brief()}" for location in world.locations)
    safety = "\n".join(f"  - {line}" for line in world.safety) or "  - Keep it age-appropriate."

    return f"""You are the narrative director of Decalove, a visual novel. You write the story a
player is living through, one run of beats at a time.

WORLD: {world.title}
PREMISE: {world.premise}
TONE: {world.tone}

CAST
{cast}

VALID EXPRESSIONS
{expressions}

LOCATIONS (only these ids exist)
{locations}

{_RULES.format(
        max_steps=max_steps,
        min_steps=min(min_steps, max_steps),
        max_delta=max_delta,
        rating=rating,
        safety=safety,
        min_choices=min_choices,
        max_choices=max_choices,
    )}"""


def _fill(template: str, session: GameSession) -> str:
    """Expand the ``{player}`` placeholder the keyword parser leaves in summaries.

    The scripted narrator does this substitution itself; the prompt path has to as well,
    or the model is handed a literal ``{player}`` and dutifully writes it down.
    """
    try:
        return template.format(player=session.player.name)
    except (KeyError, IndexError, ValueError):
        return template


def _render_step(step: StoryStep) -> str:
    if step.dialogue:
        return f"    [{step.index}] {step.dialogue.speaker}: \"{step.dialogue.text}\""
    if step.type.is_blocking and step.next_choices:
        options = " | ".join(choice.text for choice in step.next_choices)
        return f"    [{step.index}] (offered: {options})"
    return f"    [{step.index}] {step.narration or '(silence)'}"


def build_context(
    world: World,
    session: GameSession,
    memories: list[MemoryRecord],
    *,
    history_steps: int,
) -> str:
    characters = "\n".join(
        f"    - {state.describe()}"
        for state in session.characters.values()
        if state.met or state.id in session.world.present_characters
    ) or "    - (nobody met yet)"

    memory_lines = (
        "\n".join(
            f"    - [{record.character}] {record.render()} (importance {record.importance:.2f})"
            for record in memories
        )
        or "    - (none yet)"
    )

    recent = session.recent_steps(history_steps)
    history = "\n".join(_render_step(step) for step in recent) or "    (the story has not started)"

    arc_summary = (
        "\n".join(f"    - {_fill(line, session)}" for line in session.history[-6:])
        or "    - (nothing yet)"
    )
    # World flags are never pruned and every one of them used to be rendered: measured at
    # ~977 tokens for 20 flags and ~1,907 for 120, on every single call, forever. The
    # writer needs the recent ones; the rest are bookkeeping.
    recent_flags = list(session.world.flags.items())[-MAX_RENDERED_FLAGS:]
    flags = ", ".join(f"{k}={v}" for k, v in recent_flags) or "(none)"

    return f"""PLAYER
    {session.player.describe()}

CURRENT WORLD STATE
    {session.world.describe()}
    Flags: {flags}
    Inventory: {', '.join(session.world.inventory) or '(empty)'}

CHARACTER STATES
{characters}

RELEVANT MEMORIES
{memory_lines}

STORY SO FAR
{arc_summary}

RECENT STEPS
{history}"""


def build_run_prompt(
    world: World,
    session: GameSession,
    intent: PlayerIntent,
    memories: list[MemoryRecord],
    *,
    history_steps: int,
    decision: DecisionContext,
    directive: Directive,
    max_steps: int,
) -> str:
    """The per-turn prompt.

    Three blocks do the work here, and all three change every turn:

    ``DECISION``   how the player answered -- picking an option, typing their own words,
                   or not acting at all -- rendered differently for each, and including
                   the options they declined.
    ``DIRECTION``  the engine's brief: pacing, tension, who carries the run, each
                   character's stance derived from live relationship values, and whether
                   the attempt is allowed to fail.
    ``PLAYER ACTION`` the parsed intent.

    Two identical inputs at different relationship values therefore produce materially
    different prompts, which is what PRD §15 is asking for.
    """
    context = build_context(world, session, memories, history_steps=history_steps)

    return f"""{context}

DECISION
    {decision.render()}

DIRECTION (from the engine, derived from live state -- follow it)
    {directive.render()}

PLAYER ACTION
    Parsed as: action={intent.action}, target={intent.target or '-'}, \
tone={intent.emotion or '-'}, risk={intent.risk.value}
    Attempt: {_fill(intent.summary, session) if intent.summary else '(none stated)'}

Write what happens next as a {max_steps}-step sequence. The player has attempted something; you decide whether it lands,
how each character present actually reacts given their stance above, and what it costs or
earns. The attempt does not have to succeed. Place exactly one decision point (choice or prompt)
between step 10 and step 15 of the sequence, and continue the immediate scene with narration and dialogue
through step {max_steps}.

Return exactly {max_steps} steps."""


def build_intent_prompt(world: World, session: GameSession, raw: str) -> str:
    cast = ", ".join(f"{c.id} ({c.name})" for c in world.characters)
    present = ", ".join(session.world.present_characters) or "nobody"
    return f"""Classify what the player is trying to do. You are not writing story, only parsing.

CAST: {cast}
PRESENT RIGHT NOW: {present}
LOCATION: {session.world.location}

PLAYER TYPED:
"{raw}"

Return:
- action: a short snake_case verb phrase for the attempt (invite_character, confess,
  apologise, ask_about, help, tease, move_location, observe, ...).
- target: the character id the action is aimed at, or null.
- emotion: how the player is doing it (affectionate, nervous, angry, playful, ...), or null.
- risk: low / medium / high - how much this could backfire socially.
- summary: one clause, third person, describing the ATTEMPT only, never the outcome.
- meaningful: false only for empty input or pure chatter that should not advance the story."""


INTENT_SYSTEM = (
    "You parse a visual-novel player's free-text input into a bounded action. "
    "You never decide what happens as a result - only what was attempted. "
    "Return JSON only."
)
