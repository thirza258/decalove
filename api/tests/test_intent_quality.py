"""Compound intent and narrative quality — the intelligence PRD's FR-04 and FR-03."""

from __future__ import annotations

import pytest

from app.agents.narrative import NarrativeAgent, RunResult
from app.agents.quality import NarrativeQualityEvaluator, QualityContext
from app.agents.scripted import ScriptedNarrator
from app.domain.direction import DecisionContext, DecisionKind, Directive
from app.domain.intent import IntentComponent, PlayerIntent
from app.domain.quality import QualityDimension
from app.domain.story import GeneratedRun, GeneratedStep


def beat(**kwargs):
    return GeneratedStep(**{
        "type": "narration", "location": "classroom", "characters": ["aiko"],
        "narration": "Aiko holds the blue notebook open.", **kwargs,
    })


def question(texts=("Offer to help.", "Ask what it is for.", "Say you cannot stay.")):
    return beat(type="choice", narration="Aiko waits for an answer.", next_choices=[
        {"id": f"c{i}", "text": text} for i, text in enumerate(texts)
    ])


class TestCompoundIntent:
    def test_two_attempts_are_read_from_one_sentence(self, director, session):
        intent = director.parse_keywords(
            session, "I apologise to Aiko, but I defend Ren."
        )
        assert intent.action == "apologise" and intent.target == "aiko"
        components = {(component.action, component.target) for component in intent.components}
        assert ("apologise", "aiko") in components
        assert any(target == "ren" for _action, target in components)
        assert intent.targets[:2] == ["aiko", "ren"]

    def test_a_simple_sentence_still_has_one_component(self, director, session):
        intent = director.parse_keywords(session, "I apologise to Aiko.")
        assert len(intent.components) == 1
        assert intent.components[0].target == "aiko"

    def test_legacy_construction_gets_a_primary_component(self):
        intent = PlayerIntent(action="talk_to", target="aiko")
        assert intent.components[0].action == "talk_to"
        assert intent.components[0].target == "aiko"

    async def test_the_model_reading_resolves_targets_and_risks(self, world, session):
        class StubChat:
            name = "stub"
            async def complete_json(self, **kwargs):
                return {
                    "action": "apologise", "target": "Aiko", "emotion": "remorse",
                    "risk": "medium", "summary": "apologises to Aiko",
                    "meaningful": True, "confidence": 0.4, "ambiguity": True,
                    "overall_emotion": "remorse",
                    "components": [
                        {"action": "apologise", "target": "Aiko", "emotion": "remorse",
                         "intensity": 0.8, "priority": 1, "confidence": 0.9,
                         "quote": "apologise to Aiko"},
                        {"action": "defend", "target": "Ren", "emotion": "protective",
                         "intensity": 0.7, "priority": 2, "confidence": 0.8,
                         "quote": "defend Ren"},
                    ],
                }

        from app.agents.director import DirectorAgent

        intent = await DirectorAgent(world, chat=StubChat()).parse(session, "sorry but also defend")
        assert intent.components[0].target == "aiko"
        assert intent.components[1].target == "ren"
        assert intent.components[1].action == "defend"
        assert intent.ambiguity is True and intent.confidence == 0.4

    def test_planning_puts_both_targets_in_the_scene(self, director, session):
        session.world.present_characters = ["mika", "haruto"]
        intent = director.parse_keywords(session, "I apologise to Aiko, but I defend Ren.")
        plan = director.plan(session, intent, DecisionContext(kind=DecisionKind.free_text, typed="x"))
        assert {"aiko", "ren"}.issubset(set(plan.focus))


class TestQualityRubric:
    def context(self, session, **kwargs):
        return QualityContext(
            session=session,
            intent=kwargs.pop("intent", PlayerIntent(action="help", target="aiko", raw="help")),
            directive=kwargs.pop("directive", Directive()),
            **kwargs,
        )

    def test_repetition_is_detected_against_delivered_prose(self, session):
        evaluator = NarrativeQualityEvaluator()
        repeated = "Aiko holds the blue notebook open."
        report = evaluator.evaluate(
            [beat(narration=repeated), question()],
            self.context(session, recent_beats=[repeated]),
        )
        assert report.scores[QualityDimension.repetition.value] < 0.5
        assert any(issue.dimension is QualityDimension.repetition for issue in report.issues)

    def test_player_agency_violations_are_reported_not_hidden(self, session):
        report = NarrativeQualityEvaluator().evaluate(
            [beat(), question()],
            self.context(session, validator_rules=["player_agency"]),
        )
        assert report.scores[QualityDimension.player_agency.value] < 1.0
        assert any(issue.severity == "high" for issue in report.issues)

    def test_a_menu_of_paraphrases_scores_badly(self, session):
        report = NarrativeQualityEvaluator().evaluate(
            [beat(), question(("Say nothing.", "Say nothing at all.", "Stay silent."))],
            self.context(session),
        )
        assert report.scores[QualityDimension.choice_quality.value] < 0.6
        assert any(issue.dimension is QualityDimension.choice_quality
                   for issue in report.issues)

    def test_a_distinct_menu_scores_well(self, session):
        report = NarrativeQualityEvaluator().evaluate(
            [beat(), question(("Offer to help with the page.", "Ask why she is upset.",
                               "Tell her you cannot stay."))],
            self.context(session),
        )
        assert report.scores[QualityDimension.choice_quality.value] >= 0.55

    def test_a_secret_only_another_character_holds_is_a_knowledge_violation(
        self, session, world
    ):
        from app.domain.knowledge import CharacterKnowledge, KnowledgeType

        secret = CharacterKnowledge(
            id="k1", game_id=session.id, character_id="aiko",
            fact_id="secret:aiko", proposition=f"her own secret: {world.character('aiko').secret}",
            knowledge_type=KnowledgeType.known, metadata={"own_secret": True},
        )
        step = beat(dialogue={
            "speaker": "ren", "text": world.character("aiko").secret,
        }, narration=None)
        report = NarrativeQualityEvaluator().evaluate(
            [step, question()],
            self.context(session, knowledge={"aiko": [secret]}),
        )
        assert any(issue.dimension is QualityDimension.knowledge_consistency
                   for issue in report.issues)

    def test_the_report_is_serialisable_for_regression_analysis(self, session):
        report = NarrativeQualityEvaluator().evaluate([beat(), question()], self.context(session))
        payload = report.model_dump(mode="json")
        assert set(payload["scores"]) == {dimension.value for dimension in QualityDimension}
        assert 0.0 <= payload["overall_score"] <= 1.0

    async def test_the_optional_judge_refines_taste_but_not_engine_observations(self, session):
        from test_llm_path import StubChat

        chat = StubChat({
            "overall_score": 0.5,
            "scores": [
                {"dimension": "character_voice", "score": 0.2},
                {"dimension": "player_agency", "score": 0.0},
                {"dimension": "repetition", "score": 0.9},
            ],
            "issues": [{"dimension": "character_voice", "severity": "medium",
                        "description": "the voices blur together"}],
            "repairable": True,
        })
        evaluator = NarrativeQualityEvaluator(judge=chat)
        context = self.context(session)
        rubric = evaluator.evaluate([beat(), question()], context)
        report = await evaluator.evaluate_with_judge([beat(), question()], context, rubric)

        assert report.evaluator == "llm"
        assert report.scores["character_voice"] == 0.2
        assert report.scores["repetition"] == 0.9
        assert report.scores["player_agency"] == 1.0, "the judge may not whitewash agency"
        assert any(issue.description == "the voices blur together" for issue in report.issues)

    async def test_a_broken_judge_leaves_the_rubric_in_place(self, session):
        from app.llm.base import LLMError
        from test_llm_path import StubChat

        evaluator = NarrativeQualityEvaluator(judge=StubChat(error=LLMError("down")))
        context = self.context(session)
        rubric = evaluator.evaluate([beat(), question()], context)
        report = await evaluator.evaluate_with_judge([beat(), question()], context, rubric)
        assert report is rubric


class TestQualityRepair:
    def agent(self, world, validator, narrator, **kwargs):
        return NarrativeAgent(
            world, validator, narrator,
            quality=NarrativeQualityEvaluator(max_repairs=1), **kwargs,
        )

    async def test_repair_drops_a_repeated_beat_and_survives_revalidation(
        self, world, validator, narrator, session
    ):
        agent = self.agent(world, validator, narrator)
        repeated = "Aiko holds the blue notebook open."
        steps = [beat(narration=repeated), beat(narration=repeated), question()]
        result = agent._finish(
            GeneratedRun(steps=steps, summary="Aiko waits."), session,
            used_fallback=False, provider="test",
        )
        repaired = await agent._evaluate(
            result, session,
            PlayerIntent(action="help", target="aiko", raw="help"),
            DecisionContext(kind=DecisionKind.free_text, typed="help"),
            Directive(), None,
        )
        texts = [step.narration for step in repaired.steps]
        assert texts.count(repeated) == 1, "the duplicate beat was not removed"
        assert any(step.is_blocking for step in repaired.steps)
        assert repaired.repair_attempts == 1

    async def test_a_repair_that_cannot_survive_validation_is_discarded(
        self, world, validator, narrator, session, monkeypatch
    ):
        agent = self.agent(world, validator, narrator)
        result = agent._finish(
            GeneratedRun(steps=[beat(), question()], summary="Aiko waits."), session,
            used_fallback=False, provider="test",
        )
        # A repair that narrates the player's decision must be truncated by the
        # Validator; if nothing usable remains, the original run is kept.
        monkeypatch.setattr(
            agent, "_repair_steps",
            lambda steps, report: [GeneratedStep(
                type="narration", location="classroom", characters=["aiko"],
                narration="You kiss Aiko.",
            )],
        )
        monkeypatch.setattr(
            NarrativeQualityEvaluator, "should_repair", lambda self, report: True
        )
        repaired = await agent._evaluate(
            result, session,
            PlayerIntent(action="help", target="aiko", raw="help"),
            DecisionContext(kind=DecisionKind.free_text, typed="help"),
            Directive(), None,
        )
        assert repaired is result, "an unrepairable run replaced the validated original"
        assert any(step.is_blocking for step in repaired.steps)

    async def test_a_paraphrasing_menu_is_rewritten_by_the_writer(
        self, world, validator, narrator, session
    ):
        from test_llm_path import StubChat

        replacement = [
            "Offer to help with the page.",
            "Ask why she is upset.",
            "Tell her you cannot stay.",
        ]
        chat = StubChat({"choices": replacement, "rationale": "distinct intentions"})
        agent = self.agent(world, validator, narrator, choice_repair_enabled=True)
        result = agent._finish(
            GeneratedRun(steps=[
                beat(),
                question(("Say nothing.", "Say nothing at all.", "Stay silent.")),
            ], summary="Aiko waits."),
            session, used_fallback=False, provider="stub",
        )
        result.provider_obj = chat

        repaired = await agent._evaluate(
            result, session,
            PlayerIntent(action="help", target="aiko", raw="help"),
            DecisionContext(kind=DecisionKind.free_text, typed="help"),
            Directive(), None,
        )
        blocking = next(step for step in repaired.steps if step.is_blocking)
        assert [choice.text for choice in blocking.next_choices] == replacement
        assert len(chat.calls) == 1, "the menu repair must be one bounded call"
        assert repaired.repair_attempts == 1

    async def test_a_failed_menu_rewrite_falls_back_to_deterministic_repair(
        self, world, validator, narrator, session
    ):
        from app.llm.base import LLMError
        from test_llm_path import StubChat

        agent = self.agent(world, validator, narrator, choice_repair_enabled=True)
        result = agent._finish(
            GeneratedRun(steps=[
                beat(),
                question(("Say nothing.", "Say nothing at all.", "Stay silent.")),
            ], summary="Aiko waits."),
            session, used_fallback=False, provider="stub",
        )
        result.provider_obj = StubChat(error=LLMError("menu writer offline"))

        repaired = await agent._evaluate(
            result, session,
            PlayerIntent(action="help", target="aiko", raw="help"),
            DecisionContext(kind=DecisionKind.free_text, typed="help"),
            Directive(), None,
        )
        blocking = next(step for step in repaired.steps if step.is_blocking)
        assert blocking.next_choices, "a failed rewrite cost the player their menu"
        assert len(blocking.next_choices) >= validator.min_choices

    def test_repair_is_bounded_by_configuration(self, world, session):
        evaluator = NarrativeQualityEvaluator(max_repairs=0)
        report = NarrativeQualityEvaluator().evaluate(
            [beat(), question(("Say nothing.", "Say nothing at all.", "Stay silent."))],
            QualityContext(
                session=session,
                intent=PlayerIntent(action="help", target="aiko"),
                directive=Directive(),
            ),
        )
        assert evaluator.should_repair(report) is False
