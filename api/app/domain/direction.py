"""Direction — what the engine tells the writer before the writer writes.

PRD §9.1 gives the Director Agent more to do than parse intent: narrative direction,
pacing, which characters participate, which events matter. That planning happens here,
**deterministically, in the engine** -- never by asking a model what it should do next.
PRD §33 again: the LLM writes prose; the engine decides the shape of the scene.

The payoff is that two identical player inputs produce different scenes, because the
directive derived from state differs. PRD §15's example -- insulting Aiko at affection 60
is a playful argument, at 20 it is a real fight -- is implemented as
:class:`Stance.conflict_mode`.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class DecisionKind(str, Enum):
    """How the player arrived at this turn. Each one earns a different prompt."""

    opening = "opening"
    choice = "choice"
    free_text = "free_text"
    auto = "auto"


class Pacing(str, Enum):
    quiet = "quiet"
    building = "building"
    charged = "charged"
    release = "release"


class DecisionContext(BaseModel):
    """Everything about *how* the player answered, not just what they answered.

    ``rejected`` is the part that is usually thrown away. What a player declined is
    real information -- three options were offered, they took one, and the two they
    passed on say something about who they are playing as.
    """

    model_config = ConfigDict(extra="ignore")

    kind: DecisionKind = DecisionKind.free_text
    step_id: str | None = None
    chosen_text: str | None = None
    rejected: list[str] = Field(default_factory=list)
    typed: str | None = None
    used_free_text_when_offered_choices: bool = False

    def render(self) -> str:
        """The DECISION block of the prompt. Deliberately different per kind."""
        if self.kind is DecisionKind.choice:
            lines = [f'The player chose: "{self.chosen_text}"']
            if self.rejected:
                passed = " / ".join(f'"{option}"' for option in self.rejected)
                lines.append(f"    They were also offered, and passed on: {passed}")
                lines.append(
                    "    Write the chosen line as something they meant. You may let the "
                    "roads not taken register as absence -- what they did NOT say can be "
                    "conspicuous -- but never narrate them saying it."
                )
            return "\n    ".join(lines)

        if self.kind is DecisionKind.free_text:
            lines = [f'The player wrote, in their own words: "{self.typed}"']
            lines.append(
                "    They typed this rather than picking from a list, so honour its "
                "specifics: the exact thing they mentioned, the way they phrased it, and "
                "anything oddly particular about it. Do not smooth it into a generic beat."
            )
            if self.used_free_text_when_offered_choices:
                lines.append(
                    "    Options were on offer and they wrote their own instead -- they are "
                    "reaching for something the menu did not contain."
                )
            return "\n    ".join(lines)

        if self.kind is DecisionKind.auto:
            return (
                "No input from the player: the scene is continuing under its own weight.\n"
                "    Keep this run small and observational. Do not introduce a new "
                "development; let the moment breathe and hand control back quickly."
            )

        return "The story is beginning. Establish the scene and the people in it."


class Stance(BaseModel):
    """How one character is disposed toward the player *right now* — PRD §15."""

    model_config = ConfigDict(extra="ignore")

    character: str
    posture: str
    note: str
    conflict_mode: str = "playful"
    receptive: bool = True

    def render(self) -> str:
        return f"{self.character} is {self.posture}. {self.note} (conflict reads as: {self.conflict_mode})"


class PlayerStyle(BaseModel):
    """A rolling profile of how this player plays. Persisted with the save.

    Not shown to the player and not a score -- it exists so the writing can meet them
    where they are, the way a human GM adjusts to the table.
    """

    model_config = ConfigDict(extra="ignore")

    typed: int = 0
    chosen: int = 0
    bold: int = 0
    cautious: int = 0
    targets: dict[str, int] = Field(default_factory=dict)

    @property
    def turns(self) -> int:
        return self.typed + self.chosen

    def record(self, *, kind: DecisionKind, risk: str, target: str | None) -> None:
        if kind is DecisionKind.free_text:
            self.typed += 1
        elif kind is DecisionKind.choice:
            self.chosen += 1
        if risk == "high":
            self.bold += 1
        elif risk == "low":
            self.cautious += 1
        if target:
            self.targets[target] = self.targets.get(target, 0) + 1

    @property
    def favourite(self) -> str | None:
        if not self.targets:
            return None
        return max(self.targets.items(), key=lambda item: item[1])[0]

    def note(self) -> str:
        if self.turns < 3:
            return "Too early to tell how this player likes to play."

        bits: list[str] = []
        if self.typed > self.chosen:
            bits.append("writes their own moves more often than picking from the menu")
        elif self.chosen > self.typed * 3:
            bits.append("sticks to the options offered")

        if self.bold > self.cautious:
            bits.append("goes for the risky, direct thing")
        elif self.cautious > self.bold * 2:
            bits.append("hangs back and watches before committing")

        favourite = self.favourite
        if favourite and self.targets[favourite] >= max(3, self.turns // 2):
            bits.append(f"keeps returning to {favourite}")

        return "This player " + "; ".join(bits) + "." if bits else "This player plays evenly."


class Directive(BaseModel):
    """The engine's brief for one run. Rendered into the prompt as DIRECTION."""

    model_config = ConfigDict(extra="ignore")

    pacing: Pacing = Pacing.building
    tension: int = 40
    focus: list[str] = Field(default_factory=list)
    stances: list[Stance] = Field(default_factory=list)
    beat_goal: str = ""
    allow_failure: bool = False
    push_location: str | None = None
    arc_note: str = ""
    style_note: str = ""
    max_steps: int = 20
    #: Set only by ``DirectorAgent.plan`` once the playthrough has earned an ending. It is
    #: the sole authority: the wire schema cannot express an ending, and the validator
    #: refuses to promote one unless this is true.
    is_finale: bool = False
    ending_kind: str | None = None
    ending_partner: str | None = None

    def stance_for(self, character: str) -> Stance | None:
        return next((s for s in self.stances if s.character == character), None)

    def render(self) -> str:
        if self.is_finale:
            return self._render_finale()

        lines = [
            f"Pacing: {self.pacing.value} (tension {self.tension}/100)",
            f"This run should: {self.beat_goal}",
        ]
        if self.focus:
            lines.append(f"Carry it with: {', '.join(self.focus)}")
        for stance in self.stances:
            lines.append(f"- {stance.render()}")
        if self.allow_failure:
            lines.append(
                "The attempt is allowed to fall flat. A rebuff here is more interesting "
                "than a win, and it is not the end of anything."
            )
        else:
            lines.append("The attempt should land, though not necessarily the way they expect.")
        if self.push_location:
            lines.append(
                f"The scene has been in one place too long. Move it to {self.push_location} "
                "with an explicit transition step."
            )
        if self.arc_note:
            lines.append(f"Arc: {self.arc_note}")
        if self.style_note:
            lines.append(f"Player: {self.style_note}")
        return "\n    ".join(lines)

    def _render_finale(self) -> str:
        """The DIRECTION block for the last run of the story."""
        with_whom = self.ending_partner or "nobody in particular"
        lines = [
            "THIS IS THE FINAL RUN OF THE STORY. Write an ending, not another beat.",
            f"Shape: a {self.ending_kind or 'quiet'} ending, centred on {with_whom}.",
            "Close it. No cliffhanger, no new complication, and do NOT offer the player "
            "another decision -- the engine will not present one.",
            "Land it on a concrete image rather than a summary of how everyone feels.",
            "You may describe what the player does here: there is no next choice for it "
            "to pre-empt.",
        ]
        for stance in self.stances:
            lines.append(f"- {stance.render()}")
        if self.style_note:
            lines.append(f"Player: {self.style_note}")
        return "\n    ".join(lines)
