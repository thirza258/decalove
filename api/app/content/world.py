"""World definition types.

Authored, not generated. The LLM reads these; it never edits them. This is what keeps
"Aiko" the same person across a whole playthrough (PRD §24 Rule 2) and what bounds the
set of legal locations (Rule 3).
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Character:
    id: str
    name: str
    age: int
    pronouns: str
    role: str
    personality: str
    speech: str
    appearance: str
    likes: tuple[str, ...] = ()
    dislikes: tuple[str, ...] = ()
    secret: str = ""
    default_emotion: str = "neutral"
    expressions: tuple[str, ...] = (
        "neutral",
        "happy",
        "embarrassed",
        "surprised",
        "sad",
        "angry",
        "thoughtful",
    )
    #: Two hex colours used by the Ren'Py client to draw a consistent placeholder sprite
    #: when no generated image is available (PRD §26).
    palette: tuple[str, str] = ("#8899aa", "#334455")
    starting_relationship: dict[str, int] = field(default_factory=dict)

    def brief(self) -> str:
        """Compact rendering for the system prompt."""
        likes = ", ".join(self.likes) or "—"
        dislikes = ", ".join(self.dislikes) or "—"
        return (
            f"{self.name} (id: {self.id}, {self.age}, {self.pronouns}) — {self.role}. "
            f"Personality: {self.personality} "
            f"Speech: {self.speech} "
            f"Likes: {likes}. Dislikes: {dislikes}."
        )


@dataclass(frozen=True)
class Location:
    id: str
    name: str
    description: str
    #: How the place is referred to mid-sentence ("meet me on the rooftop").
    place: str = ""
    art: str = ""
    palette: tuple[str, str] = ("#33415a", "#0f172a")
    times: tuple[str, ...] = ("morning", "afternoon", "sunset", "evening")
    #: In-world filler narration played while a batch is still generating, so the player
    #: never sees a spinner (PRD §11).
    ambience: tuple[str, ...] = ()

    @property
    def in_prose(self) -> str:
        return self.place or self.name.lower()

    def brief(self) -> str:
        return f"{self.id}: {self.name} — {self.description}"


@dataclass(frozen=True)
class World:
    id: str
    title: str
    premise: str
    tone: str
    rating: str
    characters: tuple[Character, ...]
    locations: tuple[Location, ...]
    opening_location: str
    arcs: tuple[str, ...] = ("prologue",)
    art_style: str = "anime visual novel key art, soft cel shading"
    #: What everyone in this world is wearing, emitted in every character prompt. Shared
    #: rather than repeated per character so the cast cannot drift into four different
    #: schools -- each character's own ``appearance`` then reads as a variation on it.
    wardrobe: str = ""
    #: Content boundaries handed to every generation call (PRD §28).
    safety: tuple[str, ...] = ()

    def character(self, character_id: str) -> Character | None:
        return next((c for c in self.characters if c.id == character_id), None)

    def location(self, location_id: str) -> Location | None:
        return next((loc for loc in self.locations if loc.id == location_id), None)

    @property
    def character_ids(self) -> tuple[str, ...]:
        return tuple(c.id for c in self.characters)

    @property
    def location_ids(self) -> tuple[str, ...]:
        return tuple(loc.id for loc in self.locations)

    def resolve_location(self, text: str | None) -> str | None:
        """Map a phrase the player used ('the roof', 'train station') onto a location id."""
        if not text:
            return None
        needle = text.strip().lower()
        for location in self.locations:
            for alias in (location.id, location.name, location.place):
                if alias and alias.lower() in needle:
                    return location.id
        # A couple of things players say that no field spells out.
        for alias, location_id in (("roof", "rooftop"), ("home", "player_home"), ("train", "train_station")):
            if alias in needle:
                return location_id
        return None

    def resolve_character(self, text: str | None) -> str | None:
        """Map a name the LLM or player used ('Aiko', 'aiko') onto a canonical id."""
        if not text:
            return None
        needle = text.strip().lower()
        for character in self.characters:
            if needle in (character.id.lower(), character.name.lower()):
                return character.id
        return None
