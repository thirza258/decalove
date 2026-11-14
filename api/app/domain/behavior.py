"""Player behaviour profile — the intelligence PRD's FR-07.

Characters should be able to notice a pattern in how the player plays. The profile is
evidence-based on purpose: every dimension carries the number of observations behind it,
its confidence is a function of that count, and a single action moves it by a fraction of
its range. One dramatic turn must not permanently define the player.

The profile is persisted with the save (``GameSession.behavior``) so it is committed on
the same delivery boundary as everything else. It never forces an outcome; it is context
the writer and the Director may use.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

#: Observations at which confidence reaches ~0.5 (``n / (n + EVIDENCE_HALF_LIFE)``).
EVIDENCE_HALF_LIFE = 4.0

#: How far one observation can move a dimension, relative to its full range.
OBSERVATION_WEIGHT = 0.2


class PlayerBehaviorProfile(BaseModel):
    """Seven behavioural dimensions, each in [0, 1], plus the evidence behind them."""

    model_config = ConfigDict(extra="ignore")

    sociability: float = 0.5
    conflict_response: float = 0.5
    emotional_expression: float = 0.5
    risk_tolerance: float = 0.5
    empathy: float = 0.5
    curiosity: float = 0.5
    commitment: float = 0.5

    #: Number of observations per dimension. Confidence is derived, never stored.
    evidence_count: dict[str, int] = Field(default_factory=dict)
    #: Observations that pulled against the current reading. A player who is usually
    #: empathetic and then acts coldly is not overwritten; both facts are kept.
    conflicting_evidence: dict[str, int] = Field(default_factory=dict)
    #: Step ids already folded in, so a re-delivered batch cannot double-count evidence.
    seen_steps: list[str] = Field(default_factory=list)

    updated_at_step: int = 0

    def confidence(self, dimension: str) -> float:
        count = int(self.evidence_count.get(dimension, 0))
        return count / (count + EVIDENCE_HALF_LIFE)

    def value(self, dimension: str) -> float:
        return float(getattr(self, dimension))

    def observe(self, dimension: str, target: float, *, step_id: str = "") -> None:
        """Move one dimension toward ``target`` by one observation's worth.

        ``target`` is what this single action suggests (0 or 1 for a binary signal,
        anything between for a graded one). The movement is weighted by how much
        evidence already exists, so early noise does not outvote a pattern.
        """
        # Dedupe per dimension: one delivery carries evidence on several dimensions, and
        # keying only by step id made every dimension after the first silently vanish.
        key = f"{dimension}:{step_id}" if step_id else ""
        if key and key in self.seen_steps:
            return
        if key:
            self.seen_steps.append(key)
            # Bounded: the profile is part of the save document.
            del self.seen_steps[:-200]

        current = self.value(dimension)
        if self.evidence_count.get(dimension) and abs(target - current) >= 0.5:
            self.conflicting_evidence[dimension] = (
                int(self.conflicting_evidence.get(dimension, 0)) + 1
            )
        # More evidence -> trust the running mean more, the single observation less.
        weight = OBSERVATION_WEIGHT / (1.0 + self.confidence(dimension))
        updated = current + (target - current) * weight
        setattr(self, dimension, max(0.0, min(1.0, updated)))
        self.evidence_count[dimension] = int(self.evidence_count.get(dimension, 0)) + 1

    def note(self) -> str:
        """One clause for the prompt. Silence until there is enough evidence to speak."""
        confident = [
            (dimension, self.value(dimension))
            for dimension in (
                "sociability", "conflict_response", "emotional_expression",
                "risk_tolerance", "empathy", "curiosity", "commitment",
            )
            if self.confidence(dimension) >= 0.4
        ]
        if not confident:
            return ""

        phrases: list[str] = []
        for dimension, value in confident:
            if 0.45 <= value <= 0.55:
                continue
            high = value > 0.55
            phrases.append(_PHRASES[dimension][0 if high else 1])
        return "Observers may notice the player " + ", ".join(phrases) + "." if phrases else ""

    def note_for(self, character: str, *, warmth: int = 0) -> str:
        """The same pattern, filtered through one character's disposition.

        A guarded character reads boldness as recklessness; a warm one reads it as
        courage. The profile does not change; the interpretation does.
        """
        base = self.note()
        if not base:
            return ""
        if warmth < 25:
            return base + " They are inclined to read it uncharitably."
        if warmth > 60:
            return base + " They are inclined to give the player the benefit of the doubt."
        return base


_PHRASES: dict[str, tuple[str, str]] = {
    "sociability": ("seeking people out", "keeping to themselves"),
    "conflict_response": ("meeting conflict head-on", "sidestepping confrontation"),
    "emotional_expression": ("saying what they feel", "keeping feelings under wraps"),
    "risk_tolerance": ("taking chances", "playing it safe"),
    "empathy": ("looking out for other people", "putting themselves first"),
    "curiosity": ("asking questions", "taking things as given"),
    "commitment": ("following through", "leaving things unfinished"),
}
