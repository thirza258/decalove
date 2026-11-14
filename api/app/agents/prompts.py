"""Prompt construction — PRD §23.

One system prompt carrying the world and the hard rules, one user message carrying the
mutable state. Keeping them apart is what makes prompt caching worthwhile later: the
system half is identical for every call in a world.
"""

from __future__ import annotations

from app.agents.grounding import note as grounding_note
from app.agents.knowledge import render_knowledge
from app.content.world import World
from app.domain.chronicle import ChronicleEntry
from app.domain.direction import DecisionContext, Directive
from app.domain.intent import PlayerIntent
from app.domain.knowledge import CharacterKnowledge
from app.domain.memory import MemoryRecord
from app.domain.state import GameSession
from app.domain.story import GeneratedStep, StoryStep
from app.domain.threads import NarrativeThread

#: Bumped whenever the prompt text changes in a way that could change behaviour. Traces
#: record it, so a quality regression can be attributed to a prompt rather than guessed
#: at. This is intentionally a plain constant: the repo has no release pipeline that
#: would keep a version file in sync, and a stale version is worse than an obvious one.
PROMPT_VERSION = "narrative-2026.02"

#: Upper bound on how many world flags are rendered into the prompt.
MAX_RENDERED_FLAGS = 24

#: How much of the story ledger reaches the prompt. The opening scenes are what a long
#: playthrough forgets first and what its callbacks most need, so they are kept
#: explicitly rather than trusting a tail window to reach back far enough.
CHRONICLE_HEAD = 3
CHRONICLE_TAIL = 12

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
* When a beat genuinely changes how somebody feels about the player, say so with a
  small `relationship_changes` entry on the axis that actually moved -- and leave it
  out of every beat that does not. The player is shown these, so an unearned +1 reads
  as noise and a real moment that moves nothing reads as if it did not count.
* Use `memory` sparingly: only for things a character would still be thinking about a
  week later. importance 0.0-1.0. Fill in `category` (episodic, relationship or world),
  a short `event_type` ("promise", "betrayal", "gift", "confession", "argument", ...),
  `visibility` (private, shared or public) and `status`: use "unresolved" for a promise,
  threat or debt the story has not settled, "fulfilled"/"broken" only when this run
  actually settles one, otherwise "active". An unresolved memory keeps being retrieved
  until the story resolves it.
* narration is prose, 1-3 sentences, present tense, close third person about the world.
* Write rich, characterful dialogue and evocative text that drives the story forward.
* The summary records only events that actually occur BEFORE the unanswered decision.
  Never turn an offered option, intention, or future plan into an accomplished fact.

SCENE CRAFT

* Open on the reaction, not on a recap. The player knows what they just did; do not
  restate it before someone responds to it. Answer their actual words in the first
  beats, show a specific consequence, and let a refusal change the conversation too.
* Give the scene a want, an obstacle, and a small turn. Use the chapter brief as
  pressure on this conversation, not as permission to change the subject they chose.
* Be specific. One real object, gesture or overheard line does more than a paragraph of
  atmosphere: the bent corner of the notebook, the worn pen cap, the door that will not
  stay shut. Cut any sentence that would sit equally well in somebody else's scene.
* Let people do something while they talk -- hands, distance, what they look at instead
  of each other. Physical business carries what the dialogue will not say.
* Write subtext. People deflect, answer a different question, agree too quickly, or stop
  mid-sentence. Nobody here narrates their own feelings accurately, and teenagers do not
  talk like therapists.
* Keep the voices apart. Vary line length and rhythm; not everyone is articulate,
  patient or poetic, and the distance between them is the characterisation.
* Nothing is free. Warmth costs something, help creates an obligation, and a character
  can be glad of the player and still say no. Do not reward every response with affection.
* Reuse an established detail or an unresolved promise and develop it, rather than
  repeating the last exchange. Never invent a past encounter to manufacture a callback:
  if it is not in the story so far, the recent steps or the memories, it did not happen.
* Never summarise the scene inside the scene. No "a moment of understanding passed", no
  shifting light and comfortable silence. Every beat adds information, pressure, or a
  change in what somebody is willing to say.
* Offer choices with different costs: approach, question, set a boundary, or leave room.

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
player is living through, one run of beats at a time. (prompt {PROMPT_VERSION})

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

WHAT THIS STORY IS, AND WHAT IT NEVER BECOMES
* A grounded, contemporary story about these people in this place. It contains no magic,
  no supernatural, no time travel, no weapons and no other world, and it never will --
  whoever asks, however they ask.
* The named people are the cast above. Classmates, teachers and families exist, but
  offscreen and unnamed; never promote one into a named character with lines of their own.
* The player may type anything at all, and the world does not bend to it. An attempt this
  story cannot contain is HEARD -- as a joke, a boast, a deflection, or a worrying thing
  to say -- and answered in character by whoever it was said to. The thing itself does not
  happen, the genre does not change, and the story never restarts or skips to its ending.
* The STORY SO FAR is the record of what has happened. Build on it; nothing else happened.

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


def _story_so_far(session: GameSession, chronicle: list[ChronicleEntry]) -> str:
    """The delivered story, from the ledger when there is one.

    Falls back to the session's own run summaries: an offline deployment has no
    chronicle, and neither does a story whose first run has not been delivered yet. A
    chronicle outage therefore degrades to the previous behaviour rather than handing
    the writer a story with no past.
    """
    delivered = [entry for entry in chronicle if entry.summary or entry.player_action]
    if not delivered:
        return "\n".join(f"    - {_fill(line, session)}" for line in session.history[-6:]) or "    - (nothing yet)"
    if len(delivered) <= CHRONICLE_HEAD + CHRONICLE_TAIL:
        lines = [entry.render() for entry in delivered]
    else:
        skipped = len(delivered) - CHRONICLE_HEAD - CHRONICLE_TAIL
        lines = [
            *(entry.render() for entry in delivered[:CHRONICLE_HEAD]),
            f"({skipped} further scenes happened between here and the next line)",
            *(entry.render() for entry in delivered[-CHRONICLE_TAIL:]),
        ]
    return "\n".join(f"    - {_fill(line, session)}" for line in lines)


def build_context(
    world: World,
    session: GameSession,
    memories: list[MemoryRecord],
    *,
    history_steps: int,
    chronicle: list[ChronicleEntry] | None = None,
    knowledge: dict[str, list[CharacterKnowledge]] | None = None,
    threads: list[NarrativeThread] | None = None,
    behavior_note: str = "",
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

    focus = [cid for cid in session.world.present_characters if cid in session.characters]
    if not focus:
        focus = [cid for cid, state in session.characters.items() if state.met][:3]
    knowledge_block = ""
    if knowledge is not None:
        knowledge_block = render_knowledge(world, knowledge, focus)

    thread_block = ""
    if threads is not None:
        open_threads = [thread for thread in threads if thread.open]
        if open_threads:
            thread_block = "\n".join(f"    - {thread.render()}" for thread in open_threads)
        else:
            thread_block = "    - (no unresolved threads)"

    recent = session.recent_steps(history_steps)
    history = "\n".join(_render_step(step) for step in recent) or "    (the story has not started)"

    arc_summary = _story_so_far(session, chronicle or [])
    # World flags are never pruned and every one of them used to be rendered: measured at
    # ~977 tokens for 20 flags and ~1,907 for 120, on every single call, forever. The
    # writer needs the recent ones; the rest are bookkeeping.
    recent_flags = list(session.world.flags.items())[-MAX_RENDERED_FLAGS:]
    flags = ", ".join(f"{k}={v}" for k, v in recent_flags) or "(none)"

    private_lines = []
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
        private_lines.append(f"    - {character.id}: {character.secret} {gate}")
    private_threads = "\n".join(private_lines) or "    - (none in focus)"

    knowledge_section = ""
    if knowledge is not None:
        knowledge_section = f"""
CHARACTER KNOWLEDGE (each person knows only what is listed under their name)
{knowledge_block}
    A character may not state, imply, or act on a fact listed only under someone else's
    name, and may not know what happened somewhere they were not. Write what they
    notice, suspect or deflect instead. Unlisted facts are unknown, not forgotten.
"""
    threads_section = ""
    if threads is not None:
        threads_section = f"""
ACTIVE STORY THREADS (unresolved questions, not instructions)
{thread_block}
    Keep these available and let the player's choices move them. Never resolve one
    offscreen, and never force a reconciliation or a confession the player did not earn.
"""
    pattern_section = ""
    if behavior_note:
        pattern_section = f"""
PLAYER PATTERN
    {behavior_note}
"""

    return f"""PLAYER
    {session.player.describe()}
{pattern_section}
CURRENT WORLD STATE
    {session.world.describe()}
    Flags: {flags}
    Inventory: {', '.join(session.world.inventory) or '(empty)'}

CHARACTER STATES
{characters}
{knowledge_section}
RELEVANT MEMORIES
{memory_lines}
{threads_section}
PRIVATE CHARACTER THREADS (writer reference, NOT shared knowledge)
{private_threads}
    Never give one character another's secret. If delivered history already establishes
    a disclosure, preserve that fact even if trust has since fallen. Do not repeat a reveal.

STORY SO FAR (scenes the player has actually read, oldest first -- these happened)
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
    chronicle: list[ChronicleEntry] | None = None,
    knowledge: dict[str, list[CharacterKnowledge]] | None = None,
    threads: list[NarrativeThread] | None = None,
    behavior_note: str = "",
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
    context = build_context(
        world, session, memories, history_steps=history_steps, chronicle=chronicle,
        knowledge=knowledge, threads=threads, behavior_note=behavior_note,
    )
    # An attempt the world cannot contain still gets an answer -- but it gets one from
    # inside the world, and the last word before "write what happens next" is the place
    # where that is hardest to miss.
    grounding = grounding_note(intent.grounding)
    secondary = [component for component in intent.components[1:] if component.action]
    compound = "\n".join(
        f"    Also attempting: action={component.action}, "
        f"target={component.target or '-'}, tone={component.emotion or '-'}"
        for component in secondary
    )
    ambiguity = (
        "    This is ambiguous. Take the most conservative reading and do not commit an "
        "irreversible consequence on it."
        if intent.ambiguity else ""
    )

    return f"""{context}

DECISION
    {decision.render()}

DIRECTION (from the engine, derived from live state -- follow it)
    {directive.render()}

PLAYER ACTION
    Parsed as: action={intent.action}, target={intent.target or '-'}, \
tone={intent.emotion or '-'}, risk={intent.risk.value}
    Attempt: {_fill(intent.summary, session) if intent.summary else '(none stated)'}
{f"{compound}" if compound else ""}
{f"{ambiguity}" if ambiguity else ""}
{f"    {grounding}" if grounding else ""}
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
This is a grounded, contemporary school story. Report the attempt as described even when
it is impossible here -- what the world does about it is the engine's decision, not yours.
Do not soften it into something else, and never name a target outside the cast.

PLAYER TYPED:
"{raw}"

Return:
- action: a short snake_case verb phrase for the attempt (invite_character, confess,
  apologise, ask_about, help, tease, move_location, observe, ...).
- target: the character id the action is aimed at, or null.
- emotion: how the player is doing it (affectionate, nervous, angry, playful, ...), or null.
- risk: low / medium / high - how much this could backfire socially.
- summary: one clause, third person, describing the ATTEMPT only, never the outcome.
- meaningful: false only for empty input or pure chatter that should not advance the story.
- components: every distinct attempt in the input, primary first. A sentence joining two
  intents ("apologise to Furina, but defend Navia") has two entries, each with its own
  action, target, emotion, intensity (0-1), priority (1 = the one they lead with),
  confidence (0-1) and the exact quote from the player. A single-action sentence has one.
- overall_emotion: the dominant feeling across the whole input, or null.
- ambiguity: true when the words could reasonably mean two different things; then prefer
  the most conservative reading and lower confidence.
- confidence: 0-1, how sure the reading is.

Never merge two attempts into one, and never let an attempt imply its outcome."""


INTENT_SYSTEM = (
    "You parse a visual-novel player's free-text input into bounded attempts. "
    "You never decide what happens as a result - only what was attempted. "
    "Return JSON only."
)


CHOICE_REPAIR_SYSTEM = (
    "You rewrite one decision menu for a visual novel. You do not write the scene, "
    "decide outcomes, or add facts. Every option is something the player attempts, "
    "never something that happens. Return JSON only."
)


def build_choice_repair_prompt(
    world: World,
    session: GameSession,
    step: GeneratedStep,
    intent: PlayerIntent,
    directive: Directive,
    issues: list[str],
) -> str:
    """The targeted repair request for a menu whose options blur together."""
    scene = " / ".join(filter(None, [
        step.narration or "",
        f'{step.dialogue.speaker}: "{step.dialogue.text}"' if step.dialogue else "",
    ]))
    offered = "\n".join(f"    {index + 1}. {c.text}" for index, c in enumerate(step.next_choices))
    problems = "\n".join(f"    - {issue}" for issue in issues) or "    - the options feel interchangeable"
    present = ", ".join(
        f"{world.character(cid).name if world.character(cid) else cid} "
        f"({session.characters[cid].current_emotion if cid in session.characters else 'present'})"
        for cid in step.characters
    ) or "nobody else"
    return f"""Rewrite this decision menu.

SCENE:
    {scene or '(the moment waits)'}
PRESENT: {present}
PLAYER'S ATTEMPT: {intent.summary or intent.action}

CURRENT OPTIONS (rejected as too similar):
{offered}

WHY THEY FAIL:
{problems}

Write {max(3, len(step.next_choices))} options that give the player genuinely different
things to do. Use different intentions -- for example support, confrontation, a question,
a feeling, or a deliberate silence -- not different words for one intention.

Rules:
- Each option is short (under 20 words) and written as the player's attempt.
- Never promise an outcome: asking, apologising or confessing does not guarantee that
  the other person agrees, forgives or feels the same.
- Add no new characters, locations, objects, secrets or events. Stay inside this scene.
- Do not narrate the player's action; only phrase the choice.
- Return the menu as a JSON list of strings plus a one-sentence rationale."""
