"""Choosing which ending a playthrough has earned — PRD §16.

The obvious design is absolute thresholds ("romance if romance >= 60"). It is wrong for
this world. Look at the authored starting values: Ren opens at friendship 25 / trust 14,
Aiko at friendship 0 / trust 18. An absolute platonic floor would hand a player who did
nothing a Ren friendship ending, and would punish someone who spent the whole game
patiently earning Aiko's trust from a lower base.

So the ending ranks characters by how far the player *moved* them from where they started.
"""

from __future__ import annotations

from enum import Enum

from app.content.world import World
from app.domain.state import GameSession

#: Total growth below this and nobody got close enough for the story to be about them.
GROWTH_FLOOR = 20

#: How much a point of anger costs against growth. See ``growth_for``.
ANGER_WEIGHT = 2


class EndingKind(str, Enum):
    romance = "romance"
    friendship = "friendship"
    solo = "solo"


def _bond(relationship: dict[str, int]) -> tuple[int, int]:
    romantic = int(relationship.get("romance", 0)) + int(relationship.get("affection", 0))
    platonic = int(relationship.get("friendship", 0)) + int(relationship.get("trust", 0))
    return romantic, platonic


def growth_for(world: World, session: GameSession, character_id: str) -> tuple[int, int, int]:
    """``(overall, romantic_growth, platonic_growth)`` against the authored baseline."""
    state = session.characters.get(character_id)
    if state is None:
        return (0, 0, 0)

    authored = world.character(character_id)
    baseline = dict(authored.starting_relationship) if authored else {}

    romantic_now, platonic_now = _bond(state.relationship)
    romantic_was, platonic_was = _bond(baseline)

    romantic = romantic_now - romantic_was
    platonic = platonic_now - platonic_was
    # Anger is weighted heavily on purpose. Deltas are capped at +/-5 a step, so reaching
    # anger 60 takes a dozen deliberately hostile beats -- and a romance ending with
    # someone who is furious with you is the wrong story to tell about that playthrough.
    overall = max(romantic, platonic) - ANGER_WEIGHT * state.value("anger")
    return (overall, romantic, platonic)


def choose_ending(
    world: World, session: GameSession, *, growth_floor: int = GROWTH_FLOOR
) -> tuple[EndingKind, str | None]:
    """Which ending, and with whom. Deterministic, including ties."""
    ranked: list[tuple[int, str, int, int]] = []
    for character_id, state in session.characters.items():
        if not state.met:
            continue
        if world.character(character_id) is None:
            # No authored baseline means growth would be measured from zero, which would
            # crown a stranger left over from an older version of the world.
            continue
        overall, romantic, platonic = growth_for(world, session, character_id)
        ranked.append((overall, character_id, romantic, platonic))

    if not ranked:
        return EndingKind.solo, None

    focus = session.player.romance_focus

    def rank(row: tuple[int, str, int, int]) -> tuple[int, int, int, str]:
        overall, character_id, _, _ = row
        state = session.characters[character_id]
        # Ties break on: growth, then the romance the player asked for at setup, then how
        # often they sought this character out, then trust, then id. Fully determined, so
        # the same save always ends the same way.
        return (
            overall,
            1 if focus and character_id == focus else 0,
            session.style.targets.get(character_id, 0),
            state.value("trust"),
            character_id,
        )

    overall, character_id, romantic, platonic = max(ranked, key=rank)

    if overall < growth_floor:
        return EndingKind.solo, None
    if romantic > platonic:
        return EndingKind.romance, character_id
    return EndingKind.friendship, character_id
