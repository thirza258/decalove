"""Narrative metrics from generation traces — the intelligence PRD's FR-08 §5.38.

Traces are the raw material; this turns a game's (or a benchmark run's) traces into the
metrics the PRD names: agency and knowledge violation counts, repetition and choice
diversity from the quality report, fallback and repair rates, latency and provider token
usage. Everything is computed from persisted rows, so a regression can be compared
between prompt versions or models without replaying a single model call.

Deliberately no storage of its own: a report is a projection, and a projection that
disagrees with the traces would be worse than no report.
"""

from __future__ import annotations

from collections import Counter

from pydantic import BaseModel, ConfigDict, Field

from app.domain.trace import NarrativeTrace


class NarrativeMetrics(BaseModel):
    model_config = ConfigDict(extra="ignore")

    runs: int = 0
    committed: int = 0
    delivered: int = 0
    delivery_rate: float = 0.0

    fallback_rate: float = 0.0
    repair_rate: float = 0.0

    mean_latency_ms: float | None = None
    p95_latency_ms: float | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    mean_total_tokens: float | None = None

    prompt_versions: dict[str, int] = Field(default_factory=dict)
    models: dict[str, int] = Field(default_factory=dict)
    providers: dict[str, int] = Field(default_factory=dict)
    validator_violations: dict[str, int] = Field(default_factory=dict)

    quality_runs: int = 0
    quality_mean: float | None = None
    quality_dimensions: dict[str, float] = Field(default_factory=dict)
    quality_issues: dict[str, int] = Field(default_factory=dict)
    player_agency_violations: int = 0
    knowledge_violations: int = 0
    repetition_mean: float | None = None
    choice_diversity_mean: float | None = None


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 3) if values else None


def _percentile(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = max(0, min(len(ordered) - 1, int(round(fraction * len(ordered))) - 1))
    return round(ordered[index], 1)


def summarize(traces: list[NarrativeTrace]) -> NarrativeMetrics:
    """Aggregate one selection of traces into the PRD's metric set.

    ``player_agency_violations`` and ``knowledge_violations`` are counted from quality
    issues, which are produced by the engine-side rubric and cannot be talked down by a
    model judge. A trace without a quality report simply does not contribute to the
    quality means -- it is not treated as a perfect run.
    """
    metrics = NarrativeMetrics(runs=len(traces))
    if not traces:
        return metrics

    latencies: list[float] = []
    token_totals: list[int] = []
    quality_scores: list[float] = []
    repetition: list[float] = []
    choices: list[float] = []
    dimensions: dict[str, list[float]] = {}

    for trace in traces:
        metrics.committed += int(trace.committed)
        metrics.delivered += int(trace.delivered)
        if trace.latency_ms:
            latencies.append(float(trace.latency_ms))
        token_totals.append(int(trace.total_tokens))
        metrics.prompt_tokens += trace.prompt_tokens
        metrics.completion_tokens += trace.completion_tokens
        metrics.total_tokens += trace.total_tokens
        metrics.prompt_versions[trace.prompt_version or "unknown"] = (
            metrics.prompt_versions.get(trace.prompt_version or "unknown", 0) + 1
        )
        if trace.model:
            metrics.models[trace.model] = metrics.models.get(trace.model, 0) + 1
        if trace.provider:
            metrics.providers[trace.provider] = metrics.providers.get(trace.provider, 0) + 1
        for rule in trace.validator_rules:
            metrics.validator_violations[rule] = metrics.validator_violations.get(rule, 0) + 1

        quality = trace.quality or {}
        if not quality:
            continue
        metrics.quality_runs += 1
        overall = quality.get("overall_score")
        if isinstance(overall, (int, float)):
            quality_scores.append(float(overall))
        for name, value in (quality.get("scores") or {}).items():
            if isinstance(value, (int, float)):
                dimensions.setdefault(name, []).append(float(value))
        for issue in quality.get("issues") or []:
            dimension = str(issue.get("dimension", "unknown"))
            metrics.quality_issues[dimension] = metrics.quality_issues.get(dimension, 0) + 1
            if dimension == "player_agency":
                metrics.player_agency_violations += 1
            elif dimension == "knowledge_consistency":
                metrics.knowledge_violations += 1

    metrics.delivery_rate = round(metrics.delivered / metrics.runs, 3)
    metrics.fallback_rate = round(sum(t.used_fallback for t in traces) / len(traces), 3)
    metrics.repair_rate = round(sum(t.repair_attempts > 0 for t in traces) / len(traces), 3)
    metrics.mean_latency_ms = _mean(latencies)
    metrics.p95_latency_ms = _percentile(latencies, 0.95)
    metrics.mean_total_tokens = _mean([float(value) for value in token_totals])
    metrics.quality_mean = _mean(quality_scores)
    metrics.quality_dimensions = {
        name: _mean(values) for name, values in sorted(dimensions.items())
        if _mean(values) is not None
    }
    metrics.repetition_mean = metrics.quality_dimensions.get("repetition")
    metrics.choice_diversity_mean = metrics.quality_dimensions.get("choice_quality")
    return metrics


def summarize_by_prompt_version(
    traces: list[NarrativeTrace],
) -> dict[str, NarrativeMetrics]:
    """One report per prompt version, for comparing a change against its baseline."""
    grouped: dict[str, list[NarrativeTrace]] = {}
    for trace in traces:
        grouped.setdefault(trace.prompt_version or "unknown", []).append(trace)
    return {version: summarize(rows) for version, rows in sorted(grouped.items())}


def summarize_by_model(traces: list[NarrativeTrace]) -> dict[str, NarrativeMetrics]:
    grouped: dict[str, list[NarrativeTrace]] = {}
    for trace in traces:
        grouped.setdefault(trace.model or "unknown", []).append(trace)
    return {model: summarize(rows) for model, rows in sorted(grouped.items())}


def regressions(
    baseline: NarrativeMetrics, candidate: NarrativeMetrics
) -> list[str]:
    """The release gates of §13.4, stated as comparisons rather than opinions.

    Only increases in harm and losses are reported: a candidate that is simply different
    is not a regression, and quality mean is reported separately by the caller.
    """
    problems: list[str] = []
    if candidate.knowledge_violations > baseline.knowledge_violations:
        problems.append(
            f"knowledge violation rate rose: {baseline.knowledge_violations} -> "
            f"{candidate.knowledge_violations}"
        )
    if candidate.player_agency_violations > baseline.player_agency_violations:
        problems.append(
            f"player agency violations rose: {baseline.player_agency_violations} -> "
            f"{candidate.player_agency_violations}"
        )
    if (
        baseline.repetition_mean is not None and candidate.repetition_mean is not None
        and candidate.repetition_mean < baseline.repetition_mean - 0.05
    ):
        problems.append(
            f"narrative repetition increased (repetition score "
            f"{baseline.repetition_mean} -> {candidate.repetition_mean})"
        )
    if (
        baseline.quality_mean is not None and candidate.quality_mean is not None
        and candidate.quality_mean < baseline.quality_mean - 0.05
    ):
        problems.append(
            f"narrative quality dropped: {baseline.quality_mean} -> {candidate.quality_mean}"
        )
    if (
        baseline.mean_latency_ms is not None and candidate.mean_latency_ms is not None
        and candidate.mean_latency_ms > baseline.mean_latency_ms * 1.5
    ):
        problems.append(
            f"generation latency rose more than 50%: {baseline.mean_latency_ms} -> "
            f"{candidate.mean_latency_ms} ms"
        )
    return problems


def issue_counts(traces: list[NarrativeTrace]) -> Counter[str]:
    """Raw issue tallies, for a fuller dashboard than the regression gates."""
    counts: Counter[str] = Counter()
    for trace in traces:
        for issue in (trace.quality or {}).get("issues") or []:
            counts[str(issue.get("dimension", "unknown"))] += 1
    return counts
