"""Visual Agent — PRD §9.5 (what to draw), §18 (how to prompt it), §19 (when not to).

The important output is not the prompt, it is the **cache key**. Two scenes on the
rooftop at sunset with Aiko looking surprised must resolve to the same key, or the game
regenerates art it already owns on every single beat.

Consistency (why a sprite prompt is so much narrower than it looks): a generated image is
only as stable as the request behind it, so every field that varies is a field that can
hand back a different-looking person. Three rules follow.

1. **A sprite is of a character, not of a scene.** ``make_transparent_character_png``
   strips the background off every sprite before it is composited over separately
   generated scenery, so putting the location and hour in the prompt buys nothing and
   costs everything: the discarded scenery re-lights, re-grades and re-frames the
   character on its way out. It also multiplied the sprite set by every location and time
   of day -- roughly 670 independently generated sprites where 28 would do, each one
   another chance to draw somebody else.
2. **Every varying field is a closed set.** ``expression`` already was; ``pose`` was free
   text off the model, which re-opened the same hole through a different field.
3. **Identity leads, variation follows, style closes.** The parts that must not drift are
   emitted first and identically every time; the one clause that should differ sits in
   the middle where it still reads.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

from app.content.world import World
from app.domain.enums import POSES
from app.domain.state import GameSession
from app.domain.story import GeneratedStep, VisualSpec

#: Bump when prompt construction changes enough that old art should not be reused.
#: v2: sprites dropped scene context and closed the pose set, so v1 art is a different
#: picture of a different person and must not be served alongside v2.
CACHE_NAMESPACE = "v2"

#: Framing shared by every sprite, verbatim. A sprite set that is framed differently from
#: one image to the next reads as a different character even when the face matches.
SPRITE_FRAMING = (
    "half body portrait, waist up, facing viewer, visual novel character sprite, "
    "clean transparent background, isolated on white background"
)

#: Negatives that belong to a *kind* of image rather than to taste. Merged with the
#: deployment-wide IMAGE_NEGATIVE_PROMPT.
SPRITE_NEGATIVE = "background scenery, landscape, multiple characters, full body, cropped head"
BACKGROUND_NEGATIVE = "people, person, character, figures, portrait"

#: Seeds are drawn from here. 2^31 keeps them inside what every sampler accepts.
_SEED_SPACE = 2**31


@dataclass(frozen=True)
class AssetSpec:
    kind: str
    cache_key: str
    prompt: str
    #: Suppressed terms, for backends that take them. SDXL does; the hosted image API
    #: does not, and ignores it.
    negative: str = ""
    #: Fixed starting noise, derived from *what the image is of* rather than from the
    #: prompt: every picture of Aiko shares a seed whatever her expression, so the
    #: sampler starts each one from the same face. ``None`` leaves it to the sampler.
    seed: int | None = None

    def to_payload(self) -> dict:
        """JSON-safe form, for the trip to the image worker.

        Derived from the fields rather than listed by hand: the hand-written version
        dropped every field added after it, which is a silent downgrade -- images seeded
        and negated in-process and neither under Celery, i.e. exactly the deployment that
        generates them.
        """
        return asdict(self)

    @classmethod
    def from_payload(cls, payload: dict) -> "AssetSpec":
        return cls(**payload)


def _key(namespace: str, payload: dict[str, str | None]) -> str:
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    digest = hashlib.blake2b(canonical.encode("utf-8"), digest_size=10).hexdigest()
    return f"{namespace}_{digest}"


def _seed(*parts: str) -> int:
    """A stable seed for a subject.

    Deliberately *not* derived from the prompt: the point is that Aiko-happy and Aiko-sad
    share a seed, and their prompts differ. Deriving it from the subject is what makes
    them the same person wearing two expressions.
    """
    digest = hashlib.blake2b("\x1f".join(parts).encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big") % _SEED_SPACE


class VisualAgent:
    def __init__(
        self,
        world: World,
        *,
        deterministic_seed: bool = True,
        seed_salt: str = "",
        style_prompt: str = "",
        negative_prompt: str = "",
        character_scene_context: bool = False,
        character_pose_variants: bool = False,
    ) -> None:
        self.world = world
        self.deterministic_seed = deterministic_seed
        self.seed_salt = seed_salt
        #: The world's own art direction unless the deployment overrides it.
        self.style_prompt = style_prompt.strip() or world.art_style
        self.negative_prompt = negative_prompt.strip()
        self.character_scene_context = character_scene_context
        self.character_pose_variants = character_pose_variants

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
            spec.pose = self._normalise_pose(spec.pose)

        spec.time_of_day = spec.time_of_day or session.world.time_of_day
        spec.weather = spec.weather or session.world.weather
        return spec

    def _normalise_pose(self, pose: str | None) -> str | None:
        """Snap a pose onto the closed set, or drop it.

        ``expression`` has always been closed this way. ``pose`` was not, so the writer
        could invent one -- and each invention is another sprite of the same character,
        generated from scratch, free to look like somebody else.
        """
        if not self.character_pose_variants:
            return None
        candidate = (pose or "").strip().lower()
        return candidate if candidate in POSES else None

    # -- asset specs ---------------------------------------------------------------------

    def _negatives(self, *kind_specific: str) -> str:
        return ", ".join(part for part in (*kind_specific, self.negative_prompt) if part)

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
                self.style_prompt,
            )
            if part
        )
        # Seeded on the place alone, so the rooftop at sunset and the rooftop at noon are
        # the same rooftop in two lights rather than two different rooftops.
        return AssetSpec(
            kind="background",
            cache_key=key,
            prompt=prompt,
            negative=self._negatives(BACKGROUND_NEGATIVE),
            seed=self._seed_for("location", self.world.id, location.id),
        )

    def character_spec(self, spec: VisualSpec) -> AssetSpec | None:
        if not spec.character:
            return None
        character = self.world.character(spec.character)
        if character is None:
            return None
        location = self.world.location(spec.background) if self.character_scene_context else None
        pose = spec.pose if self.character_pose_variants else None

        key = _key(
            "ch",
            {
                "ns": CACHE_NAMESPACE,
                "world": self.world.id,
                "character": character.id,
                "expression": spec.expression,
                "pose": pose,
                # Both are None unless character_scene_context is on, which keeps the
                # sprite set at character x expression rather than multiplying it by
                # every place and hour the character is ever seen in.
                "location": location.id if location else None,
                "time": spec.time_of_day if self.character_scene_context else None,
            },
        )
        prompt = ", ".join(
            part
            for part in (
                # Identity first and always identical: what the model reads earliest is
                # what it commits to hardest.
                f"{character.name}, {character.age} year old student",
                character.appearance,
                # After the individual description, so the shared costume reads as the
                # thing each character's own line varies rather than the other way round.
                self.world.wardrobe,
                # The one clause that is meant to differ, before the boilerplate so it
                # still carries weight against a locked seed.
                f"{spec.expression} expression" if spec.expression else None,
                pose,
                f"at the {location.in_prose}" if location else None,
                spec.time_of_day if (location and self.character_scene_context) else None,
                SPRITE_FRAMING,
                self.style_prompt,
            )
            if part
        )
        # Seeded on the character alone -- not the expression, not the prompt. This is
        # what makes every sprite of Aiko start from the same face.
        return AssetSpec(
            kind="character",
            cache_key=key,
            prompt=prompt,
            negative=self._negatives(SPRITE_NEGATIVE),
            seed=self._seed_for("character", self.world.id, character.id),
        )

    def _seed_for(self, *parts: str) -> int | None:
        if not self.deterministic_seed:
            return None
        return _seed(self.seed_salt, *parts)

    def specs_for(self, spec: VisualSpec) -> list[AssetSpec]:
        return [s for s in (self.background_spec(spec), self.character_spec(spec)) if s]
