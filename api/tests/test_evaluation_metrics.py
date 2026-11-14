"""Metrics and regression gates over persisted traces — FR-08 §5.38 and §13.4."""

from __future__ import annotations

from app.domain.quality import NarrativeQualityReport, QualityDimension, QualityIssue
from app.domain.trace import NarrativeTrace
from app.llm.base import record_usage, reset_usage, take_usage
from app.services.evaluation import (
    regressions,
    summarize,
    summarize_by_model,
    summarize_by_prompt_version,
)


def trace(**overrides) -> NarrativeTrace:
    payload = dict(
        id="t1", game_id="g1", batch_id="b1", prompt_version="narrative-2026.02",
        provider="openrouter", model="model-a", latency_ms=1000.0,
        prompt_tokens=100, completion_tokens=200, total_tokens=300,
        committed=True, delivered=True,
    )
    payload.update(overrides)
    return NarrativeTrace(**payload)


def quality(overall=0.8, **scores) -> dict:
    base = {dimension.value: 0.8 for dimension in QualityDimension}
    base.update(scores)
    return NarrativeQualityReport(
        overall_score=overall, scores=base, issues=[],
    ).model_dump(mode="json")


class TestSummary:
    def test_empty_selection_is_zeroed_not_undefined(self):
        metrics = summarize([])
        assert metrics.runs == 0 and metrics.delivery_rate == 0.0
        assert metrics.mean_latency_ms is None

    def test_rates_tokens_latency_and_versions_are_aggregated(self):
        rows = [
            trace(id="a", latency_ms=1000, total_tokens=300),
            trace(id="b", latency_ms=3000, total_tokens=500, used_fallback=True,
                  repair_attempts=1),
            trace(id="c", latency_ms=2000, total_tokens=400, prompt_version="old",
                  model="model-b", delivered=False),
        ]
        metrics = summarize(rows)
        assert metrics.runs == 3
        assert metrics.fallback_rate == round(1 / 3, 3)
        assert metrics.repair_rate == round(1 / 3, 3)
        assert metrics.mean_latency_ms == 2000.0
        assert metrics.total_tokens == 1200
        assert metrics.mean_total_tokens == 400.0
        assert metrics.prompt_versions == {"narrative-2026.02": 2, "old": 1}
        assert metrics.delivery_rate == round(2 / 3, 3)

    def test_validator_and_quality_issues_are_counted_per_dimension(self):
        report = {
            "overall_score": 0.5,
            "scores": {"player_agency": 0.5, "knowledge_consistency": 0.0,
                       "repetition": 0.3, "choice_quality": 0.4},
            "issues": [
                {"dimension": "player_agency", "severity": "high", "description": "agency"},
                {"dimension": "knowledge_consistency", "severity": "high",
                 "description": "leak"},
            ],
        }
        metrics = summarize([
            trace(quality=report, validator_rules=["continuity", "player_agency"]),
        ])
        assert metrics.quality_runs == 1
        assert metrics.quality_mean == 0.5
        assert metrics.player_agency_violations == 1
        assert metrics.knowledge_violations == 1
        assert metrics.validator_violations == {"continuity": 1, "player_agency": 1}
        assert metrics.repetition_mean == 0.3
        assert metrics.choice_diversity_mean == 0.4

    def test_traces_without_quality_do_not_count_as_perfect_runs(self):
        metrics = summarize([trace(quality={}), trace(quality=quality(0.6))])
        assert metrics.quality_runs == 1
        assert metrics.quality_mean == 0.6

    def test_versions_and_models_split_into_comparable_reports(self):
        rows = [
            trace(id="a", prompt_version="v1", model="m1"),
            trace(id="b", prompt_version="v2", model="m1"),
            trace(id="c", prompt_version="v2", model="m2"),
        ]
        versions = summarize_by_prompt_version(rows)
        models = summarize_by_model(rows)
        assert {version: report.runs for version, report in versions.items()} == {
            "v1": 1, "v2": 2,
        }
        assert {model: report.runs for model, report in models.items()} == {
            "m1": 2, "m2": 1,
        }


class TestRegressionGates:
    def test_an_unchanged_run_reports_nothing(self):
        report = summarize([trace(quality=quality(0.8))])
        assert regressions(report, report) == []

    def test_new_knowledge_or_agency_leaks_are_regressions(self):
        baseline = summarize([trace(id="a")])
        candidate = summarize([trace(id="b", quality={
            "overall_score": 0.8,
            "scores": {},
            "issues": [
                {"dimension": "knowledge_consistency", "severity": "high",
                 "description": "leak"},
                {"dimension": "player_agency", "severity": "high", "description": "agency"},
            ],
        })])
        problems = regressions(baseline, candidate)
        assert any("knowledge" in problem for problem in problems)
        assert any("agency" in problem for problem in problems)

    def test_more_repetition_and_lower_quality_are_regressions(self):
        baseline = summarize([trace(quality=quality(0.8, repetition=0.9))])
        candidate = summarize([trace(quality=quality(0.6, repetition=0.5))])
        problems = regressions(baseline, candidate)
        assert any("repetition" in problem for problem in problems)
        assert any("quality" in problem for problem in problems)

    def test_latency_more_than_fifty_percent_worse_is_a_regression(self):
        baseline = summarize([trace(latency_ms=1000)])
        candidate = summarize([trace(latency_ms=2000)])
        assert any("latency" in problem for problem in regressions(baseline, candidate))

    def test_a_different_but_not_worse_run_is_not_a_regression(self):
        baseline = summarize([trace(latency_ms=1000, quality=quality(0.8))])
        candidate = summarize([trace(latency_ms=1100, quality=quality(0.82))])
        assert regressions(baseline, candidate) == []


class TestUsageAccounting:
    def test_usage_accumulates_across_retries_and_is_cleared_after_reading(self):
        reset_usage()
        record_usage({"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15})
        record_usage({"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5})
        assert take_usage() == {
            "prompt_tokens": 13, "completion_tokens": 7, "total_tokens": 20,
        }
        assert take_usage() == {
            "prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0,
        }

    def test_a_provider_that_reports_nothing_reads_as_zero(self):
        reset_usage()
        assert take_usage()["total_tokens"] == 0
