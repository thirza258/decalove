"""
Narrative Agent — PRD §9.4 and the ten-step generation of §10.

One call produces one *run*: a scene with one decision and an optional neutral tail
(docs/ARCHITECTURE.md §1.1). Everything it returns passes through the
validator before the caller sees it, and if the model is unavailable, returns garbage, or
returns something unrepairable, alternate models are tried. Web mode reports exhaustion
so the player can retry the same turn; other deployments keep the scripted fallback.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field

from app.agents.context import NarrativeContext
from app.agents.prompts import (
    CHOICE_REPAIR_SYSTEM,
    PROMPT_VERSION,
    build_choice_repair_prompt,
    build_run_prompt,
    build_system_prompt,
)
from app.agents.quality import NarrativeQualityEvaluator, QualityContext
from app.agents.scripted import ScriptedNarrator
from app.agents.validator import Validator
from app.content.world import World
from app.domain.chronicle import ChronicleEntry
from app.domain.direction import DecisionContext, DecisionKind, Directive
from app.domain.intent import PlayerIntent
from app.domain.memory import MemoryRecord
from app.domain.quality import NarrativeQualityReport, QualityDimension
from app.domain.state import GameSession
from app.domain.story import Choice, GeneratedRun, GeneratedStep
from app.domain.validation import ValidationReport
from app.llm.base import ChatProvider, LLMError, take_usage
from app.llm.dto import LLMChoiceSet, LLMRun
from app.llm.schema import strict_schema

log = logging.getLogger(__name__)

#: Beats this similar to something already delivered are repetition, not development.
_REPEAT_THRESHOLD = 0.75


@dataclass
class RunResult:
    steps: list[GeneratedStep]
    summary: str
    used_fallback: bool
    provider: str
    report: ValidationReport = field(default_factory=ValidationReport)
    quality: NarrativeQualityReport | None = None
    repair_attempts: int = 0
    prompt_chars: int = 0
    output_chars: int = 0
    prompt_version: str = PROMPT_VERSION
    model: str = ""
    #: Provider-reported usage, when the provider reports it. Zero is "not known", not
    #: "free": stubs and the scripted narrator deliberately report nothing.
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    #: The provider that produced the run. Kept so a bounded choice repair can ask the
    #: same model for a replacement menu; not persisted.
    provider_obj: object | None = None

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
        max_steps: int = 20,
        max_delta: int = 5,
        temperature: float = 0.85,
        max_tokens: int = 6000,
        history_steps: int = 20,
        rating: str = "teen",
        min_choices: int = 3,
        max_choices: int = 5,
        web_mode: bool = False,
        fallback_chats: list[ChatProvider] | None = None,
        attempt_timeout_s: float = 45.0,
        quality: NarrativeQualityEvaluator | None = None,
        choice_repair_enabled: bool = True,
        choice_repair_timeout_s: float = 20.0,
    ) -> None:
        self.world = world
        self.validator = validator
        self.scripted = scripted
        self.quality = quality
        self.choice_repair_enabled = choice_repair_enabled
        self.choice_repair_timeout_s = choice_repair_timeout_s
        self.chat = chat
        self.web_mode = web_mode
        self.fallback_chats = fallback_chats or []
        self.attempt_timeout_s = attempt_timeout_s
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
        self._finale_system = build_system_prompt(
            world, max_steps=max_steps, max_delta=max_delta, rating=rating,
            min_choices=min_choices, max_choices=max_choices, finale=True,
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
        chronicle: list[ChronicleEntry] | None = None,
        context: NarrativeContext | None = None,
    ) -> RunResult:
        decision = decision or DecisionContext(kind=DecisionKind.free_text, typed=intent.raw)
        directive = directive or Directive(max_steps=self.max_steps)
        if context is not None:
            # The assembler is the single source of truth when one is supplied; the
            # positional arguments remain for callers that build context themselves.
            memories = context.memories
            chronicle = context.chronicle

        providers = ([self.chat] if self.chat is not None else []) + self.fallback_chats
        for index, provider in enumerate(providers):
            try:
                work = self._generate_with_llm(
                    session, intent, memories, decision, directive, provider=provider,
                    chronicle=chronicle, context=context,
                )
                run, prompt_chars, usage = await asyncio.wait_for(
                    work, timeout=self.attempt_timeout_s
                )
                result = self._finish(
                    run, session, used_fallback=index > 0, provider=provider.name,
                    directive=directive,
                )
                result.prompt_chars = prompt_chars
                result.output_chars = _run_chars(run)
                result.model = getattr(provider, "model", "")
                result.prompt_tokens = usage.get("prompt_tokens", 0)
                result.completion_tokens = usage.get("completion_tokens", 0)
                result.total_tokens = usage.get("total_tokens", 0)
                result.provider_obj = provider
                if result.ok:
                    if result.report.violations:
                        log.info("validator repaired run: %s", result.report.summary())
                    result = await self._evaluate(
                        result, session, intent, decision, directive, context
                    )
                    return result
                log.warning(
                    "generated run did not survive validation (%s), falling back",
                    result.report.summary(),
                )
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning("narrative provider %s failed: %s", provider.name, exc)

        if self.web_mode:
            raise LLMError("All configured story AI models failed. Please try again.")

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
        *,
        provider: ChatProvider | None = None,
        chronicle: list[ChronicleEntry] | None = None,
        context: NarrativeContext | None = None,
    ) -> tuple[GeneratedRun, int]:
        provider = provider or self.chat
        assert provider is not None
        user = build_run_prompt(
            self.world,
            session,
            intent,
            memories,
            history_steps=self.history_steps,
            decision=decision,
            directive=directive,
            max_steps=self.max_steps,
            chronicle=chronicle,
            knowledge=(
                context.knowledge if context is not None and context.has_knowledge else None
            ),
            threads=(
                context.threads if context is not None and context.has_threads else None
            ),
            behavior_note=context.behavior_note if context is not None else "",
        )
        payload = await provider.complete_json(
            system=self._finale_system if directive.is_finale else self._system,
            user=user,
            schema_name="story_run",
            schema=self._schema,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
        )
        usage = take_usage()
        return LLMRun.model_validate(payload).to_domain(), len(user), usage

    # -- quality -----------------------------------------------------------------------

    async def _evaluate(
        self,
        result: RunResult,
        session: GameSession,
        intent: PlayerIntent,
        decision: DecisionContext,
        directive: Directive,
        context: NarrativeContext | None,
        *,
        is_opening: bool = False,
    ) -> RunResult:
        """Score the run, then ask for one deterministic repair if it is worth it.

        The repair is validated exactly like a model run, so it cannot smuggle in
        something the engine would otherwise refuse. If the repaired run does not
        survive validation, the original is kept.
        """
        if self.quality is None:
            return result

        quality_context = QualityContext(
            session=session,
            intent=intent,
            directive=directive,
            recent_beats=_recent_beats(session),
            knowledge=(
                context.knowledge if context is not None and context.has_knowledge else {}
            ),
            threads=(
                context.threads if context is not None and context.has_threads else []
            ),
            validator_rules=[violation.rule for violation in result.report.violations],
            min_choices=self.validator.min_choices,
        )
        started = time.monotonic()
        report = self.quality.evaluate(result.steps, quality_context)
        if not result.used_fallback:
            # Scripted prose is authored and already reviewed; judging it spends a model
            # call to learn what the fallback is.
            report = await self.quality.evaluate_with_judge(
                result.steps, quality_context, report
            )
        report.latency_ms = round((time.monotonic() - started) * 1000, 1)
        result.quality = report
        if not self.quality.should_repair(report):
            return result

        choice_issues = [
            issue for issue in report.issues
            if issue.dimension is QualityDimension.choice_quality and issue.repairable
        ]
        repaired_steps = self._repair_steps(result.steps, report)
        regeneration_usage: dict[str, int] = {}
        if choice_issues and self.choice_repair_enabled and not directive.is_finale:
            # A writer can find three genuinely different intentions where the
            # deterministic dedupe can only reshuffle a dull menu. One call, re-validated.
            rewritten = await self._regenerate_choices(
                result, session, intent, directive,
                [issue.description for issue in choice_issues],
            )
            if rewritten is not None:
                repaired_steps, regeneration_usage = rewritten
        if repaired_steps is None:
            return result

        candidate = self._finish(
            GeneratedRun(steps=repaired_steps, summary=result.summary),
            session,
            used_fallback=result.used_fallback,
            provider=result.provider,
            directive=directive,
            is_opening=is_opening,
        )
        if not candidate.ok:
            log.info("quality repair did not survive validation; keeping the original run")
            return result
        started = time.monotonic()
        candidate.quality = self.quality.evaluate(candidate.steps, quality_context)
        candidate.quality.latency_ms = round((time.monotonic() - started) * 1000, 1)
        if candidate.quality.overall_score < report.overall_score:
            log.info("quality repair scored worse; keeping the original run")
            return result
        candidate.repair_attempts = 1
        candidate.prompt_chars = result.prompt_chars
        candidate.output_chars = result.output_chars
        candidate.model = result.model
        candidate.prompt_version = result.prompt_version
        candidate.prompt_tokens = result.prompt_tokens + regeneration_usage.get("prompt_tokens", 0)
        candidate.completion_tokens = (
            result.completion_tokens + regeneration_usage.get("completion_tokens", 0)
        )
        candidate.total_tokens = result.total_tokens + regeneration_usage.get("total_tokens", 0)
        log.info(
            "quality repair improved %.2f -> %.2f for %s",
            report.overall_score, candidate.quality.overall_score, session.id,
        )
        return candidate

    async def _regenerate_choices(
        self,
        result: RunResult,
        session: GameSession,
        intent: PlayerIntent,
        directive: Directive,
        issues: list[str],
    ) -> tuple[list[GeneratedStep], dict[str, int]] | None:
        """Ask the writing model for a better menu. One bounded, validated attempt.

        Returns the repaired steps plus this call's usage, or ``None`` when there is no
        usable provider, no decision point, or the model cannot be trusted to answer.
        """
        provider = result.provider_obj
        if provider is None or not callable(getattr(provider, "complete_json", None)):
            return None
        index = next(
            (position for position, step in enumerate(result.steps) if step.is_blocking),
            None,
        )
        if index is None:
            return None
        blocking = result.steps[index]

        try:
            payload = await asyncio.wait_for(
                provider.complete_json(
                    system=CHOICE_REPAIR_SYSTEM,
                    user=build_choice_repair_prompt(
                        self.world, session, blocking, intent, directive, issues,
                    ),
                    schema_name="choice_set",
                    schema=strict_schema(LLMChoiceSet),
                    max_tokens=1200,
                    temperature=0.8,
                ),
                timeout=self.choice_repair_timeout_s,
            )
            usage = take_usage()
            rewritten = LLMChoiceSet.model_validate(payload)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.warning("choice repair via the writer failed; using deterministic repair",
                        exc_info=True)
            return None

        seen: set[str] = set()
        choices = []
        for text in rewritten.choices:
            text = " ".join((text or "").split())
            key = text.lower()
            if not text or key in seen:
                continue
            seen.add(key)
            choices.append(Choice(id="pending", text=text))
        if not choices:
            return None

        steps = [step.model_copy(deep=True) for step in result.steps]
        steps[index].next_choices = self.validator.renumber_choices(choices)
        return steps, usage

    def _repair_steps(
        self, steps: list[GeneratedStep], report: NarrativeQualityReport
    ) -> list[GeneratedStep] | None:
        """The one repair the rubric can make without another model call.

        Repetition is fixed by dropping the repeated beat; a samey menu is fixed by
        removing paraphrases and topping back up from the validator's scene-neutral
        bank. Anything else needs a writer, and is left reported rather than faked.
        """
        repaired = [step.model_copy(deep=True) for step in steps]
        changed = False

        repeated = [
            issue for issue in report.issues
            if issue.dimension is QualityDimension.repetition
        ]
        if repeated:
            kept: list[GeneratedStep] = []
            for step in repaired:
                text = (step.dialogue.text if step.dialogue else step.narration) or ""
                if (kept and not step.is_blocking
                        and any(_beat_overlap(text, _step_text(other)) >= _REPEAT_THRESHOLD
                                for other in kept)):
                    changed = True
                    continue
                kept.append(step)
            if kept and any(step.is_blocking for step in kept):
                repaired = kept

        blocking = next((step for step in repaired if step.is_blocking), None)
        if blocking is not None and any(
            issue.dimension is QualityDimension.choice_quality
            for issue in report.issues
        ):
            from app.agents.choices import repair as repair_choices

            offered = repair_choices(
                blocking.next_choices,
                bank=self.validator.choice_bank(blocking),
                min_choices=self.validator.min_choices,
            )
            if offered != blocking.next_choices:
                blocking.next_choices = self.validator.renumber_choices(offered)
                changed = True

        return repaired if changed else None

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
        # A repaired run may have discarded the event its summary describes. Do not
        # teach later generations that an invalid or unplayed consequence happened.
        summary = (
            self._derive_summary(report.steps)
            if any(v.rule != "run_structure" or v.remedy == "truncated" for v in report.violations)
            else run.summary.strip() or self._derive_summary(report.steps)
        )
        return RunResult(
            steps=report.steps,
            summary=summary,
            used_fallback=used_fallback,
            provider=provider,
            report=report,
        )

    @staticmethod
    def _derive_summary(steps: list[GeneratedStep]) -> str:
        lines = []
        for step in steps:
            if step.is_blocking:
                break
            if step.dialogue:
                lines.append(f"{step.dialogue.speaker}: {step.dialogue.text[:160]}")
            elif step.narration:
                lines.append(step.narration[:160])
        return " / ".join(lines[-3:]) or "The scene paused for the player's response."


def _step_text(step: GeneratedStep) -> str:
    if step.dialogue and step.dialogue.text.strip():
        return step.dialogue.text
    return step.narration or ""


def _run_chars(run: GeneratedRun) -> int:
    return sum(len(_step_text(step)) for step in run.steps) + len(run.summary or "")


def _recent_beats(session: GameSession, limit: int = 8) -> list[str]:
    beats: list[str] = []
    for step in session.steps[: session.cursor + 1][-limit:]:
        text = _step_text(step)
        if text:
            beats.append(text)
    return beats


def _shingles(text: str) -> set[tuple[str, ...]]:
    import re

    words = re.findall(r"[a-z0-9']+", (text or "").lower())
    if len(words) < 3:
        return {tuple(words)} if words else set()
    return {tuple(words[i:i + 3]) for i in range(len(words) - 2)}


def _beat_overlap(left: str, right: str) -> float:
    a, b = _shingles(left), _shingles(right)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)
