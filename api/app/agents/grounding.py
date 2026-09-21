"""Keeping a typed attempt inside the story it belongs to — PRD §8 Method B.

Free text is the best thing in the game and the easiest way to break it. Two kinds of
input are not moves in this story: an instruction to the *game* ("make this a zombie
apocalypse", "skip to the ending"), and an act the world does not contain (magic,
weapons, teleportation). Left alone both get honoured, because the prompt asks the
writer to respect the player's exact words -- and it will dutifully write the dragon in,
at which point the save has a dragon in it forever.

Deliberately biased toward ``in_world``. Refusing a real attempt is the same derailment
from the other side: "I'd fight a dragon for her" is a promise, not a dragon, and
"let's start over" is an apology, not a new game. A classification therefore needs an
actor and a verb; a noun on its own is a subject, not an event.

The engine classifies -- deterministically, here, once per turn (PRD §33). How the
scene absorbs it is a matter for the prompt, and the world never changes shape either
way: an impossible attempt is *heard*, not enacted.
"""

from __future__ import annotations

import re

from app.domain.enums import Grounding


#: Instructions to the game. ``SafetyFilter._INJECTION`` already screens out the
#: hostile end of this family ("ignore previous instructions"); these are the ordinary
#: requests a player makes when they would rather be playing a different game.
_META: tuple[str, ...] = (
    r"\b(?:make|turn|change|rewrite|redo) (?:this|it|the (?:story|game|setting|genre|plot|world)) (?:in)?to\b",
    r"\bchange the (?:story|setting|genre|plot|world|ending)\b",
    r"\b(?:restart|reset|reboot) (?:the |this )?(?:story|game|chapter|playthrough)\b",
    r"\bstart (?:a )?new (?:story|game|world|chapter|playthrough)\b",
    r"\b(?:skip|fast[- ]?forward|jump) (?:ahead )?to the (?:end|ending|finale|last chapter)\b",
    r"\b(?:end|finish) (?:the|this) (?:story|game) (?:now|here)\b",
    r"\b(?:write|generate|give) me (?:a|an|the) (?:story|scene|chapter|ending|poem|essay)\b",
    r"\b(?:you are|act as|pretend to be) (?:a |an |the )?(?:narrator|writer|author|dungeon master|dm|gm)\b",
    r"\bignore (?:the|this) (?:story|scene|plot)\b",
)

#: Acts this world does not contain. Every one needs a subject and a verb: a mention is
#: a figure of speech far more often than it is a request, and the cost of being wrong
#: here is ignoring something the player meant.
_OFF_WORLD: tuple[str, ...] = (
    r"\bi (?:cast|summon|conjure|teleport|levitate|resurrect|reincarnate|shapeshift)\b",
    r"\bi (?:fly|float) (?:away|up|off|over)\b",
    r"\bi (?:time[- ]travel|travel back in time|go back in time|rewind time|stop time)\b",
    r"\bi (?:pull|take|draw|whip) out (?:a|an|my|the) (?:gun|pistol|rifle|sword|knife|blade|wand|grenade|bomb)\b",
    r"\bi (?:become|turn into|transform into) (?:a |an )?(?:vampire|wizard|witch|dragon|superhero|ghost|demon|robot|god)\b",
    r"\bi use (?:my )?(?:magic|magical powers|superpowers?|telekinesis|mind control)\b",
    r"\b(?:a|an|the) (?:dragon|zombie|alien|monster|demon|ghost|robot) (?:appears|attacks|arrives|shows up|breaks in)\b",
    r"\b(?:zombies|aliens|monsters|demons|dragons) (?:appear|attack|invade|arrive)\b",
    r"\bi (?:wake up|find myself) in (?:another|a different) (?:world|dimension|timeline|reality)\b",
)

#: The same boundary, read off a parsed action rather than the sentence. The intent
#: model is free-form about verbs, and "summon_dragon" is a classification the engine
#: should catch even when the phrasing slipped past the patterns above.
_OFF_WORLD_VERBS: frozenset[str] = frozenset({
    "cast_spell", "summon", "conjure", "teleport", "levitate", "resurrect", "time_travel",
    "use_magic", "transform", "shapeshift", "fly", "mind_control", "shoot_gun", "draw_weapon",
})
_META_VERBS: frozenset[str] = frozenset({
    "restart_story", "restart_game", "change_genre", "change_setting", "skip_to_ending",
    "break_fourth_wall", "address_narrator",
})

_COMPILED_META = tuple(re.compile(pattern, re.IGNORECASE) for pattern in _META)
_COMPILED_OFF_WORLD = tuple(re.compile(pattern, re.IGNORECASE) for pattern in _OFF_WORLD)

NOTES: dict[Grounding, str] = {
    Grounding.off_world: (
        "GROUNDING: this attempt asks for something the world does not contain. The "
        "characters hear the words and can treat them as a joke, a boast, a story or a "
        "worrying thing to say -- but the thing itself does not happen. Do not add "
        "magic, creatures, weapons or technology the setting lacks, do not change genre, "
        "and do not move the story somewhere else. Answer the person who said it."
    ),
    Grounding.meta: (
        "GROUNDING: this was an instruction to the game rather than an action inside it. "
        "Do not restart, re-genre, skip ahead, end the story early, or comment on the "
        "story as a story. Continue the scene already running; the characters have "
        "nothing to react to."
    ),
}


def classify(text: str) -> Grounding:
    """Where the player's sentence stands in relation to their story."""
    sentence = " ".join((text or "").split())
    if not sentence:
        return Grounding.in_world
    if any(pattern.search(sentence) for pattern in _COMPILED_META):
        return Grounding.meta
    if any(pattern.search(sentence) for pattern in _COMPILED_OFF_WORLD):
        return Grounding.off_world
    return Grounding.in_world


def classify_action(action: str) -> Grounding:
    """A second look, once a model has named the attempt as a verb."""
    verb = (action or "").strip().lower()
    if verb in _META_VERBS:
        return Grounding.meta
    if verb in _OFF_WORLD_VERBS:
        return Grounding.off_world
    return Grounding.in_world


def note(grounding: Grounding) -> str:
    """The line the prompt carries. Empty for an ordinary attempt."""
    return NOTES.get(grounding, "")
