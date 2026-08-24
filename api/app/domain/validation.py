"""Validation Agent output — PRD §9.6 / §24."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from app.domain.story import GeneratedStep

Remedy = Literal["clamped", "dropped", "rewritten", "truncated", "rejected"]


class Violation(BaseModel):
    model_config = ConfigDict(extra="ignore")

    rule: str
    detail: str
    remedy: Remedy
    step_index: int | None = None

    def __str__(self) -> str:  # pragma: no cover - debug aid
        where = "run" if self.step_index is None else f"step {self.step_index}"
        return f"[{self.rule}] {where}: {self.detail} ({self.remedy})"


class ValidationReport(BaseModel):
    """Repair-then-truncate result.

    The validator never throws away a whole run for a fixable problem: it clamps what it
    can, drops the first unrepairable step and everything after it, and reports what it
    did. ``ok`` means at least one step survived.
    """

    model_config = ConfigDict(extra="ignore")

    steps: list[GeneratedStep] = Field(default_factory=list)
    violations: list[Violation] = Field(default_factory=list)

    @property
    def ok(self) -> bool:
        return bool(self.steps)

    @property
    def rejected(self) -> bool:
        return any(v.remedy == "rejected" for v in self.violations)

    def summary(self) -> str:
        if not self.violations:
            return f"{len(self.steps)} steps, clean"
        return f"{len(self.steps)} steps, {len(self.violations)} violation(s): " + "; ".join(
            str(v) for v in self.violations[:5]
        )
