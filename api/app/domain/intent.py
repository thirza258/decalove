"""Player intent — PRD §8 Method B, and the intelligence PRD's FR-04.

The player types prose; the Director Agent turns it into a bounded action. The player
states an *attempt*, never an *outcome* — the Story Agent decides what actually happens.

Compound input ("apologise to Furina, but defend Navia") carries more than one attempt.
``components`` records each one with its own target, emotion and priority; the legacy
``action``/``target`` fields remain the primary component so every existing caller keeps
working, and an ambiguous reading carries low confidence rather than being silently
resolved into a different action.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import Grounding, Risk


class IntentComponent(BaseModel):
    """One attempt inside a player's input."""

    model_config = ConfigDict(extra="ignore")

    action: str = ""
    target: str | None = None
    emotion: str | None = None
    intensity: float = 0.5
    #: 1 is the attempt the player leads with.
    priority: int = 1
    confidence: float = 0.5
    #: The clause of the player's own text this component was read from.
    quote: str = ""


class PlayerIntent(BaseModel):
    model_config = ConfigDict(extra="ignore")

    action: str = Field(description="snake_case verb, e.g. invite_character, confess, apologise")
    target: str | None = Field(default=None, description="character id the action is aimed at")
    emotion: str | None = Field(default=None, description="how the player is acting, e.g. affectionate")
    risk: Risk = Risk.medium
    summary: str = Field(default="", description="one clause restating the attempt in third person")
    meaningful: bool = Field(
        default=True,
        description="False for chatter that should not trigger a full generation cycle",
    )
    #: Where the attempt stands in relation to the world. Classified once, when the turn
    #: is accepted, and carried from there: a retry must replay the same reading of the
    #: same words, and a save written before this field existed loads as in_world.
    grounding: Grounding = Grounding.in_world
    raw: str = ""

    #: Every attempt read from the input, primary first. A single-action parse carries
    #: one component; compound input carries several with separate targets.
    components: list[IntentComponent] = Field(default_factory=list)
    overall_emotion: str | None = None
    #: True when the words could reasonably mean two different things. Ambiguous turns
    #: may not commit an irreversible consequence without further evidence.
    ambiguity: bool = False
    confidence: float = 0.5

    def model_post_init(self, __context) -> None:  # noqa: D401 - pydantic hook
        """Keep the primary fields and the component list consistent.

        Saves and callers written before components existed supply only ``action`` and
        ``target``. Materialising the primary component here means every consumer can
        rely on the list being populated.
        """
        if not self.components and (self.action or self.target):
            self.components = [
                IntentComponent(
                    action=self.action,
                    target=self.target,
                    emotion=self.emotion,
                    priority=1,
                    confidence=self.confidence,
                    quote=self.raw,
                )
            ]
        if self.overall_emotion is None:
            self.overall_emotion = self.emotion

    @property
    def targets(self) -> list[str]:
        seen: list[str] = []
        for component in self.components:
            if component.target and component.target not in seen:
                seen.append(component.target)
        if self.target and self.target not in seen:
            seen.insert(0, self.target)
        return seen

    def render(self) -> str:
        """The intent as the prompt should see it — all components, not just the first."""
        lines = [
            f"action={self.action}, target={self.target or '-'}, "
            f"tone={self.emotion or '-'}, risk={self.risk.value}"
        ]
        extras = [c for c in self.components[1:] if c.action or c.target]
        for component in extras:
            lines.append(
                f"also: action={component.action}, target={component.target or '-'}, "
                f"tone={component.emotion or '-'} (priority {component.priority})"
            )
        if self.ambiguity:
            lines.append(
                "This input is ambiguous. Prefer the most conservative reading; do not "
                "commit an irreversible consequence on the strength of it."
            )
        return "\n    ".join(lines)
