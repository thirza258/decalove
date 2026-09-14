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

1. PLAYER AGENCY. {agency_rule}
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
{decision_contract}
* When a choice is requested, provide {min_choices}-{max_choices} distinct options.
* Choice option text is what the PLAYER would say or do - written in their voice, short,
  and genuinely different from one another in intent, not in wording. Fewer than
  {min_choices} real options is worse than none: if you cannot find {min_choices}
  distinct intentions, use type "prompt" and let them write their own.
* Every step needs a `visual`. `background` must be a location id from the list.
  `expression` must come from that character's expression list. Prioritise staying within
  the established location and characters present to maintain visual continuity and reuse scene art.
* Use `memory` sparingly: only for things a character would still be thinking about a
  week later. importance 0.0-1.0.
* narration is prose, 1-3 sentences, present tense, close third person about the world.
* Write rich, characterful dialogue and evocative text that drives the story forward.
* The summary records only events that actually occur BEFORE the unanswered decision.
  Never turn an offered option, intention, or future plan into an accomplished fact.

SCENE CRAFT

* Answer the player's actual words in the first few beats. Show a specific reaction or
  consequence before introducing another problem. A refusal still changes the conversation.
* Give the scene a concrete want, an obstacle, and a small turn. Use the chapter brief
  as pressure on this conversation, not permission to ignore the player's chosen subject.
* Reveal character through conflicting wants, habits, and subtext. Preserve each voice;
  do not make everyone equally poetic, agreeable, or instantly vulnerable.
* Reuse an established detail or unresolved promise when relevant. Develop it, rather
  than repeating the last exchange. Never invent a past encounter to manufacture a callback.
* Offer choices with different costs: approach, question, set a boundary, or leave room.
  Do not reward every response with affection. Avoid filler about shifting light and
  comfortable silence; each beat must add information, pressure, or a change of perspective.

CONTENT BOUNDARIES ({rating})
{safety}"""


def decision_contract(max_steps: int, *, finale: bool = False) -> str:
    """Keep the system and turn instructions compatible, including short runs and endings."""
    if finale:
        return (
            '* This is the finale: use narration, dialogue, transition, or event steps only.\n'
            '* Do NOT emit choice or prompt steps; next_choices must be empty on every step.\n'
            '* Resolve established threads and close on a concrete image. The engine marks the ending.'
        )
    placement = (
        "between step 10 and step 15"
        if max_steps >= 15 else f"at the final step (step {max_steps})"
    )
    return (
        f'* Place exactly ONE decision point (choice or prompt) {placement}.\n'
        '* Before it, develop the consequences of the PREVIOUS player action.\n'
        '* After it, only brief, neutral narration or dialogue in the SAME location with\n'
        '  the SAME cast. These buffered beats must remain true for EVERY offered answer,\n'
        '  including refusal or silence. Never resolve or react to that unanswered choice.\n'
        '* No transitions, new events, relationship_changes, emotions, flags_set, or memory\n'
        '  after the decision. Do not advance time, introduce someone, or assume agreement.'
    )


def build_system_prompt(
    world: World,
    *,
    max_steps: int,
    max_delta: int,
    rating: str,
    min_steps: int = 3,
    min_choices: int = 3,
    max_choices: int = 5,
    finale: bool = False,
) -> str:
    cast = "\n".join(f"  - {character.brief()}" for character in world.characters)
    expressions = "\n".join(
        f"  - {character.id}: {', '.join(character.expressions)}" for character in world.characters
    )
    locations = "\n".join(f"  - {location.brief()}" for location in world.locations)
    safety = "\n".join(f"  - {line}" for line in world.safety) or "  - Keep it age-appropriate."
    agency_rule = (
        "In this epilogue, you may describe actions that follow from choices already made. "
        "Do not invent a new commitment, confession, or relationship for the player."
        if finale else
        "Never narrate a decision, speech, or deliberate action by the player. "
        "You may describe what happens to them and what others do in front of them. "
        'Bad: "You kiss Aiko." Good: "Aiko moves closer, waiting to see what you will do."'
    )

    return f"""You are the narrative director of Decalove, a visual novel. You write the story a
player is living through, one run of beats at a time.

WORLD: {world.title}
PREMISE: {world.premise}
TONE: {world.tone}

STORY THROUGHLINE (direction, not events that have already occurred)
{world.story_premise or world.premise}

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
        decision_contract=decision_contract(max_steps, finale=finale),
        agency_rule=agency_rule,
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
    parts = []
    if step.narration:
        parts.append(step.narration)
    if step.dialogue:
        parts.append(f'{step.dialogue.speaker}: "{step.dialogue.text}"')
    if step.type.is_blocking and step.next_choices:
        options = " | ".join(choice.text for choice in step.next_choices)
        parts.append(f"(offered: {options})")
    return f"    [{step.index}] {' / '.join(parts) or '(silence)'}"


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

    threads = []
    for character in world.characters:
        state = session.characters.get(character.id)
        if not state or not (state.met or character.id in session.world.present_characters):
            continue
        if not character.secret:
            continue
        may_open_up = state.value("trust") >= 45 and state.value("familiarity") >= 45
        gate = (
            "Trust supports a partial, voluntary disclosure if this conversation invites it."
            if may_open_up else
            "Keep this private; show an indirect habit or deflection instead of a disclosure."
        )
        threads.append(f"    - {character.id}: {character.secret} {gate}")
    private_threads = "\n".join(threads) or "    - (none in focus)"

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

PRIVATE CHARACTER THREADS (writer reference, NOT shared knowledge)
{private_threads}
    Never give one character another's secret. If delivered history already establishes
    a disclosure, preserve that fact even if trust has since fallen. Do not repeat a reveal.

STORY SO FAR
{arc_summary}

RECENT STEPS
{history}
    The delivery cursor is {session.cursor}. Later indices are buffered prose, not new
    player decisions. Offered options are possibilities, not actions that happened."""


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

Write what happens next as a {max_steps}-step sequence. Respond to the player's specific
attempt using the character stances and established facts above.

{decision_contract(max_steps, finale=directive.is_finale)}

Return exactly {max_steps} steps."""


def build_intent_prompt(world: World, session: GameSession, raw: str) -> str:
    cast = ", ".join(f"{c.id} ({c.name})" for c in world.characters)
    # A web batch can include continuation beats after the question. Interpret the
    # answer against what the player saw at that question, before those later beats.
    recent = session.response_context_steps(8)
    question = recent[-1] if recent and recent[-1].is_blocking else None
    present = ", ".join(question.characters if question and question.characters else session.world.present_characters) or "nobody"
    location = question.location if question else session.world.location
    conversation = "\n".join(_render_step(step) for step in recent) or "    (no dialogue yet)"
    return f"""Classify what the player is trying to do. You are not writing story, only parsing.

CAST: {cast}
PRESENT RIGHT NOW: {present}
LOCATION: {location}

CONVERSATION LEADING TO THIS RESPONSE:
{conversation}

Use this conversation to resolve references such as "her", "him", "that", or "do it".
The player's words describe their own attempt, even when it differs from every offered option.

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
