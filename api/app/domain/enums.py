from enum import Enum


class StepType(str, Enum):
    """The kind of beat a story step represents.

    ``choice`` and ``prompt`` are *blocking*: they hand control back to the player.
    See docs/ARCHITECTURE.md §1.1 — a generated run always terminates in exactly one
    blocking step, which is how PRD §10 is reconciled with §24 Rule 1 (player agency).
    """

    narration = "narration"
    dialogue = "dialogue"
    transition = "transition"
    event = "event"
    choice = "choice"
    prompt = "prompt"
    #: The last step of the story. Terminal like a decision point, but it hands control
    #: back to nobody -- see ``is_terminal``.
    ending = "ending"

    @property
    def is_blocking(self) -> bool:
        """Does this step hand control back to the player?"""
        return self in (StepType.choice, StepType.prompt)

    @property
    def is_terminal(self) -> bool:
        """Does this step end the run?

        ``is_blocking`` used to mean both things. They come apart at the ending: it stops
        the run without asking the player anything, and an ending step must NOT make
        ``GameSession.awaiting_player`` true.
        """
        return self.is_blocking or self is StepType.ending


class Risk(str, Enum):
    low = "low"
    medium = "medium"
    high = "high"


class BatchStatus(str, Enum):
    queued = "queued"
    running = "running"
    ready = "ready"
    failed = "failed"


class AssetStatus(str, Enum):
    ready = "ready"
    pending = "pending"
    unavailable = "unavailable"


#: PRD §16 relationship axes, plus ``anger`` from the §9.2 character-state example.
RELATIONSHIP_AXES: tuple[str, ...] = (
    "affection",
    "trust",
    "respect",
    "fear",
    "jealousy",
    "friendship",
    "romance",
    "familiarity",
    "anger",
)

TIMES_OF_DAY: tuple[str, ...] = ("morning", "noon", "afternoon", "sunset", "evening", "night")

#: The poses a character sprite may be drawn in. Closed for the same reason the expression
#: set is: every distinct value is a separate image of the same person, generated
#: independently, and an open field means the writer can invent "leaning against the
#: vending machine, half-turned" and get back somebody who does not look like Aiko.
POSES: tuple[str, ...] = ("standing", "arms crossed", "hands behind back", "leaning")

WEEKDAYS: tuple[str, ...] = (
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
)
