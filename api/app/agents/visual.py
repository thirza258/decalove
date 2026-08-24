"""Visual Agent — PRD §9.5 (what to draw), §18 (how to prompt it), §19 (when not to).

The important output is not the prompt, it is the **cache key**. Two scenes on the
rooftop at sunset with Aiko looking surprised must resolve to the same key, or the game
regenerates art it already owns on every single beat.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from app.content.world import World
from app.domain.state import GameSession
from app.domain.story import GeneratedStep, VisualSpec

#: Bump when prompt construction changes enough that old art should not be reused.
CACHE_NAMESPACE = "v1"


@dataclass(frozen=True)
class AssetSpec:
    kind: str
    cache_key: str
    prompt: str


def _key(namespace: str, payload: dict[str, str | None]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.blake2b(canonical.encode("utf-8"), digest_size=10).hexdigest()
    return f"{namespace}_{digest}"


class VisualAgent:
    def __init__(self, world: World) -> None:
        self.world = world

    def normalise(self, step: GeneratedStep, session: GameSession) -> VisualSpec:
        """Fill in a usable spec even when the model omitted or half-filled ``visual``."""
        spec = (step.visual or VisualSpec(background=step.location)).model_copy(deep=True)

        if self.world.location(spec.background) is None:
            spec.background = step.location if self.world.location(step.location) else session.world.location

        speaker = step.dialogue.speaker if step.dialogue else None
        candidate = spec.character or speaker or (step.characters[0] if step.characters else None)
        spec.character = self.world.resolve_character(candidate)

        if spec.character:
            character = self.world.character(spec.character)
            mood = spec.expression or step.emotion.get(spec.character)
            if character and mood not in character.expressions:
                # Keep the sprite set closed: an invented expression has no art and no
                # placeholder, so fall back to the character's resting face.
                mood = character.default_emotion if character.default_emotion in character.expressions else "neutral"
            spec.expression = mood

        spec.time_of_day = spec.time_of_day or session.world.time_of_day
        spec.weather = spec.weather or session.world.weather
        return spec

    # -- asset specs ---------------------------------------------------------------------

    def background_spec(self, spec: VisualSpec) -> AssetSpec | None:
        location = self.world.location(spec.background)
        if location is None:
            return None
        key = _key(
            "bg",
            {
                "ns": CACHE_NAMESPACE,
                "world": self.world.id,
                "location": location.id,
                "time": spec.time_of_day,
                "weather": spec.weather,
                "composition": spec.composition,
            },
        )
        prompt = ", ".join(
            part
            for part in (
                location.art or location.description,
                spec.time_of_day,
                spec.weather,
                spec.composition,
                "no people",
                self.world.art_style,
            )
            if part
        )
        return AssetSpec(kind="background", cache_key=key, prompt=prompt)

    def character_spec(self, spec: VisualSpec) -> AssetSpec | None:
        if not spec.character:
            return None
        character = self.world.character(spec.character)
        location = self.world.location(spec.background)
        if character is None:
            return None
        key = _key(
            "ch",
            {
                "ns": CACHE_NAMESPACE,
                "world": self.world.id,
                "character": character.id,
                "expression": spec.expression,
                "pose": spec.pose,
                "location": location.id if location else None,
                "time": spec.time_of_day,
            },
        )
        prompt = ", ".join(
            part
            for part in (
                f"{character.name}, {character.age} year old student",
                character.appearance,
                f"{spec.expression} expression" if spec.expression else None,
                spec.pose,
                f"at the {location.in_prose}" if location else None,
                spec.time_of_day,
                "upper body, facing viewer, transparent background",
                self.world.art_style,
            )
            if part
        )
        return AssetSpec(kind="character", cache_key=key, prompt=prompt)

    def specs_for(self, spec: VisualSpec) -> list[AssetSpec]:
        return [s for s in (self.background_spec(spec), self.character_spec(spec)) if s]
