"""Which people a story can become about.

Two things the player settles at setup meet here. The **route** decides how many people
a playthrough can end with: one, or as many as were earned. The **cast** decides who is
available at all — a romance needs the two sides to name different genders, and a side
that names none rules nothing out.

Everything downstream reads this one predicate instead of re-deriving it: the validator,
which freezes romance the story has not opened; the ending, which cannot name a partner
outside it; the Director, which passes the writer the names and nothing else; and the
offline narrator, which has no Director to tell it.
"""

from __future__ import annotations

from app.content.world import World
from app.domain.enums import Route
from app.domain.state import GameSession, PlayerProfile

#: Romance has to lead by this much, and reach this far, before a single route settles.
#: Below it the story is still open; a coin-flip lead is not a decision the player made.
ROUTE_LOCK = 35
ROUTE_MARGIN = 10

#: Written by the engine when a single route settles, and reserved so nothing else can
#: write it. Deriving the lock from live state each turn would be cheaper and wrong:
#: romance can fall, and a lock that recomputes itself hands the player a different
#: story after one bad line.
ROUTE_FLAG = "route_partner"


def _gender(pronouns: str) -> str | None:
    """What a pronoun set states, and nothing beyond it."""
    stated = (pronouns or "").strip().lower().replace(" ", "")
    if stated.startswith("she/"):
        return "f"
    if stated.startswith("he/"):
        return "m"
    return None


def romance_candidates(world: World, player: PlayerProfile) -> list[str]:
    """The cast this player's story could be about, in world order."""
    theirs = _gender(player.pronouns)
    return [
        character.id
        for character in world.characters
        if theirs is None or _gender(character.pronouns) != theirs
    ]


def locked_partner(session: GameSession) -> str | None:
    settled = session.world.flags.get(ROUTE_FLAG)
    return settled if isinstance(settled, str) and settled else None


def open_routes(world: World, session: GameSession) -> set[str]:
    """Who romance can still grow with, right now."""
    candidates = set(romance_candidates(world, session.player))
    if session.player.route is Route.harem:
        return candidates
    # The flag is the record; the setup choice stands in until one is written, so a
    # player who named someone at setup never has a turn where everyone is open.
    settled = locked_partner(session) or session.player.romance_focus
    if settled and settled in candidates:
        return {settled}
    return candidates


def settling_partner(world: World, session: GameSession) -> str | None:
    """The person a single route has just become about, if one clearly has.

    Called on delivery, next to every other state change, and only until it answers:
    once the engine has written the flag this returns nothing at all.
    """
    if session.player.route is not Route.single or locked_partner(session):
        return None
    ranked = sorted(
        (
            (session.characters[character].value("romance"),
             session.style.targets.get(character, 0),
             character)
            for character in open_routes(world, session)
            if character in session.characters
        ),
        reverse=True,
    )
    if not ranked or ranked[0][0] < ROUTE_LOCK:
        return None
    if len(ranked) > 1 and ranked[0][0] - ranked[1][0] < ROUTE_MARGIN:
        return None
    return ranked[0][2]


def note(world: World, session: GameSession) -> str:
    """The line the writer is given: names, and what everyone else is. No reasons."""
    settled = locked_partner(session)
    if session.player.route is Route.single and settled:
        return (
            f"This story has become about {settled}. "
            "Everyone else is a friendship, however close it gets."
        )
    open_now = open_routes(world, session)
    if not open_now:
        return "This is a story about friendships."
    if len(open_now) >= len(world.characters):
        return "Romance can develop with anyone here."
    names = ", ".join(character.id for character in world.characters if character.id in open_now)
    return f"Romance can develop with: {names}. Everyone else is a friendship, however close it gets."
