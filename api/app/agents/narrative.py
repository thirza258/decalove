"""
Narrative Agent — PRD §9.4 and the ten-step generation of §10.

One call produces one *run*: a linear sequence of beats that stops the moment the player
must decide again (docs/ARCHITECTURE.md §1.1). Everything it returns passes through the
validator before the caller sees it, and if the model is unavailable, returns garbage, or
returns something unrepairable, the scripted narrator takes over so the game keeps going
(PRD §26).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

from app.agents.prompts import build_run_prompt, build_system_prompt
from app.agents.scripted import ScriptedNarrator
from app.agents.validator import Validator
from app.content.world import World
from app.domain.direction import DecisionContext, DecisionKind, Directive
from app.domain.intent import PlayerIntent
from app.domain.memory import MemoryRecord
from app.domain.state import GameSession
from app.domain.story import GeneratedRun, GeneratedStep
from app.domain.validation import ValidationReport
from app.llm.base import ChatProvider, LLMError
from app.llm.dto import LLMRun
from app.llm.schema import strict_schema

log = logging.getLogger(__name__)


@dataclass
class RunResult:
    steps: list[GeneratedStep]
    summary: str
    used_fallback: bool
    provider: str
    report: ValidationReport = field(default_factory=ValidationReport)

    @property
    def ok(self) -> bool:
        return bool(self.steps)


class NarrativeAgent:
    def __init__(
        self,
        world: World,
        validator: Validator,
        scripted: ScriptedNarrator,
        *,
        chat: ChatProvider | None = None,
        max_steps: int = 10,
        max_delta: int = 5,
        temperature: float = 0.85,
        max_tokens: int = 6000,
        history_steps: int = 12,
        rating: str = "teen",
        min_choices: int = 3,
        max_choices: int = 5,
    ) -> None:
        self.world = world
        self.validator = validator
        self.scripted = scripted
        self.chat = chat
        self.max_steps = max_steps
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.history_steps = history_steps
        self._system = build_system_prompt(
            world,
            max_steps=max_steps,
            max_delta=max_delta,
            rating=rating,
            min_choices=min_choices,
            max_choices=max_choices,
        )
        self._schema = strict_schema(LLMRun)

    # -- public ------------------------------------------------------------------------

    def opening(self, session: GameSession) -> RunResult:
        """The authored opening scene.

        Deliberately not generated: New Game is instant, every playthrough gets the same
        strong hook, and the model takes over from the player's very first decision.
        """
        run = self.scripted.opening(session)
        return self._finish(run, session, used_fallback=False, provider="authored", is_opening=True)

    async def generate(
        self,
        session: GameSession,
        intent: PlayerIntent,
        memories: list[MemoryRecord],
        *,
        decision: DecisionContext | None = None,
        directive: Directive | None = None,
    ) -> RunResult:
        decision = decision or DecisionContext(kind=DecisionKind.free_text, typed=intent.raw)
        directive = directive or Directive(max_steps=self.max_steps)

        if self.chat is not None:
            try:
                run = await self._generate_with_llm(session, intent, memories, decision, directive)
            except (LLMError, ValueError) as exc:
                log.warning("narrative generation failed, falling back to scripted: %s", exc)
            else:
                result = self._finish(
                    run, session, used_fallback=False, provider=self.chat.name, directive=directive
                )
                if result.ok:
                    if result.report.violations:
                        log.info("validator repaired run: %s", result.report.summary())
                    return result
                log.warning(
                    "generated run did not survive validation (%s), falling back",
                    result.report.summary(),
                )

        run = (
            self.scripted.finale(session, directive)
            if directive.is_finale
            else self.scripted.run(session, intent, max_steps=self.max_steps, directive=directive)
        )
        return self._finish(
            run,
            session,
            used_fallback=True,
            provider=self.scripted.__class__.__name__,
            directive=directive,
        )

    # -- internals ---------------------------------------------------------------------

    async def _generate_with_llm(
        self,
        session: GameSession,
        intent: PlayerIntent,
        memories: list[MemoryRecord],
        decision: DecisionContext,
        directive: Directive,
    ) -> GeneratedRun:
        assert self.chat is not None
        payload = await self.chat.complete_json(
            system=self._system,
            user=build_run_prompt(
                self.world,
                session,
                intent,
                memories,
                history_steps=self.history_steps,
                decision=decision,
                directive=directive,
                max_steps=self.max_steps,
            ),
            schema_name="story_run",
            schema=self._schema,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
        )
        return LLMRun.model_validate(payload).to_domain()

    def _finish(
        self,
        run: GeneratedRun,
        session: GameSession,
        *,
        used_fallback: bool,
        provider: str,
        directive: Directive | None = None,
        is_opening: bool = False,
    ) -> RunResult:
        report = self.validator.validate(
            run,
            session,
            allow_ending=bool(directive and directive.is_finale),
            is_opening=is_opening,
        )
        summary = run.summary.strip() or self._derive_summary(report.steps)
        return RunResult(
            steps=report.steps,
            summary=summary,
            used_fallback=used_fallback,
            provider=provider,
            report=report,
        )

    @staticmethod
    def _derive_summary(steps: list[GeneratedStep]) -> str:
        for step in reversed(steps):
            if step.dialogue:
                return f"{step.dialogue.speaker}: {step.dialogue.text[:120]}"
            if step.narration:
                return step.narration[:120]
        return "the scene continued"
