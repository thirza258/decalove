"""The story ledger — what actually happened in one playthrough, kept.

Character memories (PRD §17) answer "what would Aiko still be thinking about?". That is
not the same question as "what has happened in this story?", and the engine had no
durable answer to the second one: the prompt renders the last handful of run summaries,
so by the festival arc the prologue has quietly fallen out of the model's world. Long
playthroughs drift, and a player's earlier choices stop mattering.

An entry is one delivered run: where it happened, what the player did to reach it, the
prose they actually read, and a digest of it for the next prompt. Written on DELIVERY,
never on generation -- a buffered beat nobody read is not part of anyone's story, and
an offered option is a possibility, not an event (docs/STORY.md).
"""

from __future__ import annotations

from datetime import datetime, timezone

from pydantic import BaseModel, ConfigDict, Field

from app.domain.story import StoryStep

#: Bounds. A 300-step playthrough is ~30 entries, so an entry has to stay small enough
#: that the whole story is a cheap read and a cheap document.
MAX_BEATS = 40
MAX_BEAT_CHARS = 400
MAX_SUMMARY_CHARS = 400
MAX_ACTION_CHARS = 300


def _clip(text: str, limit: int) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def beat_of(step: StoryStep) -> str:
    """One delivered beat as a line of story. Offered options are deliberately absent."""
    if step.dialogue and step.dialogue.text.strip():
        return _clip(f'{step.dialogue.speaker}: "{step.dialogue.text}"', MAX_BEAT_CHARS)
    return _clip(step.narration or "", MAX_BEAT_CHARS)


class ChronicleEntry(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    game_id: str
    batch_id: str
    #: The first delivered step of the run. The ordering key: batch ids are not ordered.
    index: int = 0
    last_index: int = 0
    arc: str = ""
    day: int = 1
    time_of_day: str = ""
    location: str = ""
    participants: list[str] = Field(default_factory=list)
    #: What the player did to reach this scene, in their own words where they typed them.
    player_action: str = ""
    summary: str = ""
    beats: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    delivered_at: datetime | None = None

    @staticmethod
    def key(game_id: str, batch_id: str) -> str:
        return f"{game_id}:{batch_id}"

    @classmethod
    def from_delivery(cls, game_id: str, batch_id: str, steps: list[StoryStep], *,
                      arc: str, day: int, time_of_day: str) -> ChronicleEntry:
        """Build an entry from every step of one run that has reached the player."""
        beats = [beat for beat in (beat_of(step) for step in steps) if beat][:MAX_BEATS]
        first, last = steps[0], steps[-1]
        # A run can move; recording both ends keeps a transition legible later.
        where = first.location or last.location or ""
        if last.location and last.location != first.location:
            where = f"{first.location} → {last.location}"
        participants: list[str] = []
        for step in steps:
            for character in [*step.characters, step.dialogue.speaker if step.dialogue else ""]:
                if character and character not in participants:
                    participants.append(character)
        return cls(
            id=cls.key(game_id, batch_id),
            game_id=game_id,
            batch_id=batch_id,
            index=first.index,
            last_index=last.index,
            # Time comes from the world state, which the engine advances on a scene
            # change; a step only knows what its picture should look like.
            arc=arc,
            day=day,
            time_of_day=time_of_day,
            location=where,
            participants=participants[:8],
            summary=_digest(steps),
            beats=beats,
            delivered_at=datetime.now(timezone.utc),
        )

    def render(self) -> str:
        """One line of durable context for the next prompt."""
        where = " · ".join(part for part in (self.arc, f"day {self.day}", self.location) if part)
        action = f"{self.player_action} → " if self.player_action else ""
        return f"[{where}] {action}{self.summary}".strip()


def _digest(steps: list[StoryStep]) -> str:
    """How the scene opened and where it landed.

    Deliberately built from delivered prose rather than from the model's own summary of
    the run: what the player read is the only account that cannot have drifted from it.
    Beats after the decision are excluded -- the neutral tail has to be true for every
    answer, so it says nothing about what happened.
    """
    ended = next((i for i, step in enumerate(steps) if step.is_blocking), len(steps) - 1)
    played = [beat for beat in (beat_of(step) for step in steps[: ended + 1]) if beat]
    if not played:
        return ""
    chosen = [played[0]] if len(played) == 1 else [played[0], played[-1]]
    return _clip(" … ".join(chosen), MAX_SUMMARY_CHARS)
