"""Narrative quality evaluation — the intelligence PRD's FR-03.

The Validator answers "may this be committed?". This answers "is it any good?", across
the nine dimensions the PRD names. The default evaluator is a deterministic rubric, so
it works offline, costs nothing, and cannot be prompt-injected. It uses measurable
proxies for each dimension and says so; an LLM judge can be layered on when one is
configured, because no proxy measures prose as well as a reader does.

Ordering is fixed: generation → deterministic validation → evaluation → at most one
targeted repair → deterministic validation again. A repair that fails validation is
discarded, so quality scoring can never widen what the engine accepts.
"""

from __future__ import annotations

import asyncio
import logging
import re

from app.agents.choices import MIN_GOOD_SCORE as MIN_CHOICE_SCORE
from app.agents.choices import assess as assess_choices
from app.domain.direction import Directive
from app.domain.intent import PlayerIntent
from app.domain.knowledge import CharacterKnowledge
from app.domain.quality import (
    NarrativeQualityReport,
    QualityDimension,
    QualityIssue,
)
from app.domain.state import GameSession
from app.domain.story import GeneratedStep
from app.domain.threads import NarrativeThread
from app.llm.base import ChatProvider, take_usage
from app.llm.dto import LLMQualityReport
from app.llm.schema import strict_schema

log = logging.getLogger(__name__)

QUALITY_SYSTEM = (
    "You are a demanding but fair narrative editor for an interactive visual novel. "
    "Score the scene against the dimensions given. You never rewrite it. Return JSON only."
)

_POSITIVE_EMOTIONS = frozenset({
    "happy", "affectionate", "warm", "relieved", "grateful", "hopeful", "playful",
    "excited", "fond", "content",
})
_NEGATIVE_EMOTIONS = frozenset({
    "angry", "sad", "hurt", "cold", "afraid", "anxious", "jealous", "bitter",
    "furious", "upset", "disappointed",
})
_WORD = re.compile(r"[a-z0-9']+")


def _tokens(text: str) -> set[str]:
    return {t for t in _WORD.findall((text or "").lower()) if len(t) > 2}


def _shingles(text: str, size: int = 3) -> set[tuple[str, ...]]:
    words = _WORD.findall((text or "").lower())
    if len(words) < size:
        return {tuple(words)} if words else set()
    return {tuple(words[i:i + size]) for i in range(len(words) - size + 1)}


def _overlap(left: str, right: str) -> float:
    a, b = _shingles(left), _shingles(right)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _beat(step: GeneratedStep) -> str:
    if step.dialogue and step.dialogue.text.strip():
        return step.dialogue.text
    return step.narration or ""


class QualityContext:
    """Everything the rubric needs that is not in the generated steps."""

    def __init__(
        self,
        *,
        session: GameSession,
        intent: PlayerIntent,
        directive: Directive,
        recent_beats: list[str] | None = None,
        knowledge: dict[str, list[CharacterKnowledge]] | None = None,
        threads: list[NarrativeThread] | None = None,
        validator_rules: list[str] | None = None,
        min_choices: int = 3,
    ) -> None:
        self.session = session
        self.intent = intent
        self.directive = directive
        self.recent_beats = recent_beats or []
        self.knowledge = knowledge or {}
        self.threads = threads or []
        self.validator_rules = validator_rules or []
        self.min_choices = min_choices


class NarrativeQualityEvaluator:
    def __init__(
        self,
        *,
        min_overall: float = 0.62,
        max_repairs: int = 1,
        voice_min_dialogue: int = 2,
        judge: ChatProvider | None = None,
        judge_model: str = "",
        judge_timeout_s: float = 15.0,
    ) -> None:
        self.min_overall = min_overall
        self.max_repairs = max(0, max_repairs)
        self.voice_min_dialogue = voice_min_dialogue
        #: Optional model judge. The rubric always runs first; the judge may refine the
        #: scores, never the story. When it is unavailable the rubric is the answer.
        self.judge = judge
        self.judge_model = judge_model or getattr(judge, "model", "")
        self.judge_timeout_s = judge_timeout_s

    # -- public ------------------------------------------------------------------------

    def evaluate(
        self, steps: list[GeneratedStep], context: QualityContext
    ) -> NarrativeQualityReport:
        if not steps:
            return NarrativeQualityReport(
                overall_score=0.0,
                scores={dimension.value: 0.0 for dimension in QualityDimension},
                issues=[QualityIssue(
                    dimension=QualityDimension.context_relevance,
                    severity="high",
                    description="the run contained no usable story beats",
                )],
                repairable=True,
                recommended_repairs=["regenerate the run as a scene with a decision point"],
            )

        issues: list[QualityIssue] = []
        scores: dict[str, float] = {}

        scores[QualityDimension.repetition.value], repetition_issue = self._repetition(
            steps, context
        )
        if repetition_issue:
            issues.append(repetition_issue)

        scores[QualityDimension.player_agency.value] = self._agency(context, issues)
        scores[QualityDimension.knowledge_consistency.value] = self._knowledge(
            steps, context, issues
        )
        scores[QualityDimension.context_relevance.value] = self._relevance(steps, context, issues)
        scores[QualityDimension.emotional_continuity.value] = self._emotional(steps, context, issues)
        scores[QualityDimension.causality.value] = self._causality(steps, context, issues)
        scores[QualityDimension.character_voice.value] = self._voice(steps, context, issues)
        scores[QualityDimension.narrative_progression.value] = self._progression(
            steps, context, issues
        )
        scores[QualityDimension.choice_quality.value] = self._choices(steps, context, issues)

        overall = round(sum(scores.values()) / len(scores), 3)
        repairable_issues = [issue for issue in issues if issue.repairable]
        return NarrativeQualityReport(
            overall_score=overall,
            scores={name: round(value, 3) for name, value in scores.items()},
            issues=issues,
            repairable=bool(repairable_issues) and self.max_repairs > 0,
            recommended_repairs=[issue.description for issue in repairable_issues][:3],
            evaluator="rubric",
        )

    async def evaluate_with_judge(
        self,
        steps: list[GeneratedStep],
        context: QualityContext,
        rubric: NarrativeQualityReport,
    ) -> NarrativeQualityReport:
        """Let a configured model refine the rubric's reading.

        Bounded, optional, and fail-open: a slow or broken judge leaves the deterministic
        report in place. The judge cannot raise a dimension the Validator has already
        flagged, so a model that likes a rule-breaking scene cannot whitewash it.
        """
        if self.judge is None:
            return rubric
        try:
            payload = await asyncio.wait_for(
                self.judge.complete_json(
                    system=QUALITY_SYSTEM,
                    user=_judge_prompt(steps, context, rubric),
                    schema_name="quality_report",
                    schema=strict_schema(LLMQualityReport),
                    max_tokens=2000,
                    temperature=0.1,
                ),
                timeout=self.judge_timeout_s,
            )
            assessed = LLMQualityReport.model_validate(payload)
            usage = take_usage()
        except asyncio.CancelledError:
            raise
        except Exception:
            log.warning("quality judge unavailable; keeping the rubric", exc_info=True)
            return rubric

        scores = dict(rubric.scores)
        # A dimension the rubric found seriously wrong may be lowered by the judge, never
        # raised: taste cannot overrule an observed defect.
        flagged = {
            issue.dimension.value for issue in rubric.issues if issue.severity == "high"
        }
        for entry in assessed.scores:
            try:
                dimension = QualityDimension(entry.dimension)
            except ValueError:
                continue
            if dimension.value in ("player_agency", "knowledge_consistency"):
                continue  # engine-observed, not a matter of taste
            judged = max(0.0, min(1.0, float(entry.score)))
            previous = scores.get(dimension.value, judged)
            scores[dimension.value] = min(previous, judged) if dimension.value in flagged else judged

        issues = list(rubric.issues)
        for entry in assessed.issues[:6]:
            try:
                dimension = QualityDimension(entry.dimension)
            except ValueError:
                continue
            issues.append(QualityIssue(
                dimension=dimension,
                severity=entry.severity,
                description=entry.description[:300],
            ))

        return NarrativeQualityReport(
            overall_score=round(sum(scores.values()) / len(scores), 3),
            scores={name: round(value, 3) for name, value in scores.items()},
            issues=issues,
            repairable=any(issue.repairable for issue in issues) and self.max_repairs > 0,
            recommended_repairs=[issue.description for issue in issues if issue.repairable][:3],
            evaluator="llm",
            model=self.judge_model,
            latency_ms=rubric.latency_ms,
            prompt_tokens=usage.get("prompt_tokens", 0),
            completion_tokens=usage.get("completion_tokens", 0),
            total_tokens=usage.get("total_tokens", 0),
        )

    def should_repair(self, report: NarrativeQualityReport) -> bool:
        """Repair when the run fails overall, or when a fixable structural issue exists.

        A samey menu can sit inside an otherwise well-scored run; waiting for the
        average to drop would never ask for the one repair that is cheap and safe.
        """
        structural = any(
            issue.repairable
            and issue.dimension in (
                QualityDimension.repetition,
                QualityDimension.choice_quality,
            )
            for issue in report.issues
        )
        return (
            self.max_repairs > 0
            and report.repairable
            and (not report.passes(self.min_overall) or structural)
        )

    # -- dimensions --------------------------------------------------------------------

    def _repetition(
        self, steps: list[GeneratedStep], context: QualityContext
    ) -> tuple[float, QualityIssue | None]:
        beats = [
            (position, beat)
            for position, step in enumerate(steps)
            if (beat := _beat(step))
        ]
        if len(beats) < 2 and not context.recent_beats:
            return 1.0, None
        highest = 0.0
        index = None
        for position, beat in beats:
            for earlier_position, earlier in beats:
                if earlier_position >= position:
                    break
                highest = max(highest, _overlap(beat, earlier))
            for earlier in context.recent_beats[-8:]:
                overlap = _overlap(beat, earlier)
                if overlap > highest:
                    highest = overlap
                    index = position
        score = max(0.0, min(1.0, 1.0 - highest * 1.3))
        if highest >= 0.55:
            return score, QualityIssue(
                dimension=QualityDimension.repetition,
                severity="high" if highest >= 0.75 else "medium",
                description=(
                    "A beat repeats information the player has already been told. "
                    "Advance the exchange instead of restating it."
                ),
                step_index=index,
            )
        return score, None

    def _agency(self, context: QualityContext, issues: list[QualityIssue]) -> float:
        violations = [rule for rule in context.validator_rules if rule == "player_agency"]
        if violations:
            issues.append(QualityIssue(
                dimension=QualityDimension.player_agency,
                severity="high",
                description="The prose decided something for the player; the Validator "
                            "already removed or truncated it.",
            ))
            return max(0.0, 1.0 - 0.5 * len(violations))
        return 1.0

    def _knowledge(
        self,
        steps: list[GeneratedStep],
        context: QualityContext,
        issues: list[QualityIssue],
    ) -> float:
        """Catch a character speaking a secret only another character holds.

        Secrets are the facts with an unambiguous owner-side identity; general scene
        facts are deliberately skipped, because lexical overlap cannot tell a reference
        from a coincidence and a false leak report is worse than none.
        """
        if not context.knowledge:
            return 1.0
        holders: dict[str, set[str]] = {}
        secrets: dict[str, tuple[str, set[str]]] = {}
        for holder, facts in context.knowledge.items():
            for fact in facts:
                holders.setdefault(fact.fact_id, set()).add(holder)
                if fact.metadata.get("own_secret"):
                    secrets[fact.fact_id] = (holder, _tokens(fact.proposition))

        violations = 0
        for step in steps:
            if not step.dialogue:
                continue
            speaker = step.dialogue.speaker
            spoken = _tokens(step.dialogue.text)
            if not spoken:
                continue
            for fact_id, (owner, secret_tokens) in secrets.items():
                if not secret_tokens or speaker == owner:
                    continue
                if speaker in holders.get(fact_id, set()):
                    continue
                if len(secret_tokens & spoken) / len(secret_tokens) >= 0.5:
                    violations += 1

        if violations:
            issues.append(QualityIssue(
                dimension=QualityDimension.knowledge_consistency,
                severity="high",
                description="A character referenced information they never acquired.",
            ))
            return max(0.0, 1.0 - 0.5 * violations)
        return 1.0

    def _relevance(
        self, steps: list[GeneratedStep], context: QualityContext, issues: list[QualityIssue]
    ) -> float:
        intent_tokens = _tokens(
            " ".join(filter(None, [
                context.intent.summary,
                context.intent.raw,
                context.intent.action.replace("_", " "),
                context.intent.target or "",
            ]))
        )
        if not intent_tokens:
            return 0.75
        run_text = " ".join(_beat(step) for step in steps[: max(1, len(steps) // 2)])
        run_tokens = _tokens(run_text)
        if not run_tokens:
            return 0.2
        overlap = len(intent_tokens & run_tokens) / len(intent_tokens)
        target_present = bool(context.intent.target) and context.intent.target in run_text.lower()
        score = min(1.0, 0.45 + overlap * 0.55 + (0.15 if target_present else 0.0))
        if score < 0.5:
            issues.append(QualityIssue(
                dimension=QualityDimension.context_relevance,
                severity="medium",
                description="The scene barely answers the action the player actually took.",
            ))
        return score

    def _emotional(
        self, steps: list[GeneratedStep], context: QualityContext, issues: list[QualityIssue]
    ) -> float:
        checked = 0
        inconsistent = 0
        for step in steps:
            if not step.emotion:
                continue
            for character, mood in step.emotion.items():
                checked += 1
                delta = step.relationship_changes.get(character)
                warmth = (
                    delta.affection + delta.trust + delta.friendship + delta.romance
                    if delta else 0
                )
                if mood in _NEGATIVE_EMOTIONS and warmth > 2:
                    inconsistent += 1
                elif mood in _POSITIVE_EMOTIONS and delta is not None and delta.anger > 2:
                    inconsistent += 1
        if not checked:
            # A run that asserts no feelings cannot contradict them.
            return 0.8
        score = max(0.0, 1.0 - inconsistent / checked)
        if score < 0.7:
            issues.append(QualityIssue(
                dimension=QualityDimension.emotional_continuity,
                severity="medium",
                description="An emotional reaction does not follow from the relationship "
                            "change in the same beat.",
            ))
        return score

    def _causality(
        self, steps: list[GeneratedStep], context: QualityContext, issues: list[QualityIssue]
    ) -> float:
        problems = [
            rule for rule in context.validator_rules
            if rule in ("continuity", "world_consistency")
        ]
        score = max(0.0, 1.0 - 0.4 * len(problems))
        if score < 0.7:
            issues.append(QualityIssue(
                dimension=QualityDimension.causality,
                severity="medium",
                description="A beat does not follow from the scene before it.",
            ))
        return score

    def _voice(
        self, steps: list[GeneratedStep], context: QualityContext, issues: list[QualityIssue]
    ) -> float:
        lines: dict[str, list[str]] = {}
        cast: set[str] = set()
        for step in steps:
            cast.update(step.characters)
            if step.dialogue and step.dialogue.text.strip():
                lines.setdefault(step.dialogue.speaker, []).append(step.dialogue.text)

        if not lines:
            return 0.6  # narration-only runs can be valid; they simply do not demonstrate voice

        distinctness = min(1.0, len(lines) / max(1, min(self.voice_min_dialogue, len(cast) or 1)))
        lengths = {
            speaker: sum(len(line.split()) for line in texts) / max(1, len(texts))
            for speaker, texts in lines.items()
        }
        variation = 1.0
        if len(lengths) >= 2:
            values = sorted(lengths.values())
            spread = (values[-1] - values[0]) / max(1.0, sum(values) / len(values))
            variation = min(1.0, 0.5 + spread)
        elif len(cast) >= 3:
            variation = 0.4  # a crowd scene where only one person speaks

        score = 0.6 * distinctness + 0.4 * variation
        if score < 0.5:
            issues.append(QualityIssue(
                dimension=QualityDimension.character_voice,
                severity="medium",
                description="The scene gives one voice to too much of the cast; the "
                            "characters read as interchangeable.",
            ))
        return score

    def _progression(
        self, steps: list[GeneratedStep], context: QualityContext, issues: list[QualityIssue]
    ) -> float:
        points = 0.0
        if any(step.relationship_changes for step in steps):
            points += 0.25
        if any(step.flags_set for step in steps):
            points += 0.2
        if any(step.memory for step in steps):
            points += 0.2
        if any(step.is_blocking for step in steps):
            points += 0.15
        presented = {character for step in steps for character in step.characters}
        if any(presented & set(thread.involved_characters) for thread in context.threads
               if thread.open):
            points += 0.2
        score = min(1.0, 0.35 + points)
        if score < 0.55:
            issues.append(QualityIssue(
                dimension=QualityDimension.narrative_progression,
                severity="low",
                description="The run does not appear to advance anything that was open.",
            ))
        return score

    def _choices(
        self, steps: list[GeneratedStep], context: QualityContext, issues: list[QualityIssue]
    ) -> float:
        blocking = next((step for step in steps if step.is_blocking), None)
        if blocking is None:
            return 1.0
        scene_text = " ".join(filter(None, [
            blocking.narration or "",
            blocking.dialogue.text if blocking.dialogue else "",
            context.directive.chapter_question,
        ]))
        assessment = assess_choices(
            blocking.next_choices, context_text=scene_text, min_choices=context.min_choices
        )
        if assessment.issues:
            issues.append(QualityIssue(
                dimension=QualityDimension.choice_quality,
                severity="medium" if assessment.score < MIN_CHOICE_SCORE else "low",
                description="; ".join(assessment.issues) + ".",
                step_index=next(
                    (index for index, step in enumerate(steps) if step is blocking), None
                ),
            ))
        return assessment.score


def _judge_prompt(
    steps: list[GeneratedStep], context: QualityContext, rubric: NarrativeQualityReport
) -> str:
    scene: list[str] = []
    for step in steps:
        if step.dialogue:
            scene.append(f'{step.dialogue.speaker}: "{step.dialogue.text}"')
        elif step.narration:
            scene.append(step.narration)
        if step.is_blocking and step.next_choices:
            scene.append("(offered: " + " | ".join(c.text for c in step.next_choices) + ")")
    cast = ", ".join(
        f"{character_id} ({state.current_emotion})"
        for character_id, state in context.session.characters.items()
        if state.met
    ) or "nobody met yet"
    threads = "; ".join(thread.title for thread in context.threads if thread.open) or "none"
    rubric_scores = ", ".join(f"{name} {score:.2f}" for name, score in rubric.scores.items())
    recent = "\n".join(f"    - {beat}" for beat in context.recent_beats[-5:]) or "    (none)"

    return f"""Score the generated scene. Do not rewrite it.

PLAYER ATTEMPT: {context.intent.summary or context.intent.action}
PRESENT: {cast}
OPEN THREADS: {threads}
RECENT DELIVERED LINES (for repetition checks):
{recent}

SCENE:
{chr(10).join(f"    {line}" for line in scene)}

A deterministic rubric already scored: {rubric_scores}.

Dimensions (0-1): character_voice, context_relevance, emotional_continuity, causality,
repetition (1 = no repetition), narrative_progression, choice_quality.
player_agency and knowledge_consistency are engine-observed and not yours to score.

Return overall_score, one score per dimension you can judge, and any concrete issues
(dimension, severity low/medium/high, one-sentence description). Judge the writing, not
the player's choices. A scene that obeys every rule can still be dull or
interchangeable, and that is what this pass is for."""
