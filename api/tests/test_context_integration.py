"""Context assembly, knowledge boundaries in the Validator, and quality on the batch."""

from __future__ import annotations

import pytest

from app.agents.context import ContextAssembler
from app.agents.memory_agent import MemoryAgent
from app.agents.prompts import build_context
from app.agents.quality import NarrativeQualityEvaluator
from app.domain.direction import DecisionContext, DecisionKind, Directive
from app.domain.intent import PlayerIntent
from app.domain.story import GeneratedRun, GeneratedStep, MemoryProposal, StoryStep
from app.llm.embeddings import HashingEmbedding
from app.repositories.memory_repo import (
    InMemoryChronicleRepository,
    InMemoryMemoryRepository,
)
from test_generation_service import INTENT, TYPED
from test_llm_path import StubChat, choice_step, step as llm_step
from test_narrative_benchmark import Bench


async def test_a_memory_cannot_be_formed_by_someone_who_was_not_there(
    validator, session
):
    run = GeneratedRun(steps=[
        GeneratedStep(
            type="dialogue", location="classroom", characters=["aiko"],
            dialogue={"speaker": "aiko", "text": "You came back."},
            memory={"character": "ren", "text": "Ren remembers the promise."},
        ),
        GeneratedStep(
            type="choice", location="classroom", characters=["aiko"],
            narration="Aiko waits.", next_choices=[
                {"id": "a", "text": "Offer to help."},
                {"id": "b", "text": "Ask why."},
                {"id": "c", "text": "Leave."},
            ],
        ),
    ])
    report = validator.validate(run, session)
    assert report.steps[0].memory is None
    assert any(v.rule == "knowledge_consistency" for v in report.violations)


class TestContextAssembly:
    def assembler(self, **kwargs):
        memory = MemoryAgent(HashingEmbedding(), InMemoryMemoryRepository())
        return memory, ContextAssembler(
            memory=memory,
            chronicle=InMemoryChronicleRepository(),
            max_chars=kwargs.pop("max_chars", 24000),
            **kwargs,
        )

    async def test_the_assembler_collects_memories_and_the_ledger(self, session):
        memory, assembler = self.assembler()
        await memory.remember(
            "test-game", MemoryProposal(character="aiko", text="Kai helped with the mural."),
            step_index=0,
        )
        context = await assembler.assemble(
            session, INTENT, TYPED, Directive(focus=["aiko"]),
        )
        assert context.has_knowledge is False, "no knowledge source was wired"
        assert context.memories and context.memory_ids
        assert "memories" in context.included and "chronicle" in context.included

    async def test_a_knowledge_outage_does_not_claim_nobody_knows_anything(
        self, world, session
    ):
        memory, assembler = self.assembler()
        context = await assembler.assemble(session, INTENT, TYPED, Directive(focus=["aiko"]))
        prompt = build_context(
            world, session, context.memories, history_steps=5,
            knowledge=context.knowledge if context.has_knowledge else None,
            threads=context.threads if context.has_threads else None,
        )
        assert "CHARACTER KNOWLEDGE" not in prompt

    async def test_the_budget_drops_optional_material_and_says_so(self, session):
        memory = MemoryAgent(HashingEmbedding(), InMemoryMemoryRepository())
        for index in range(40):
            await memory.remember(
                "test-game",
                MemoryProposal(
                    character="aiko",
                    text=f"A long remembered detail about the mural, number {index}, "
                         "which is deliberately verbose so the budget has to choose.",
                ),
                step_index=index,
            )
        assembler = ContextAssembler(
            memory=memory, chronicle=InMemoryChronicleRepository(), max_chars=4000,
        )
        context = await assembler.assemble(session, INTENT, TYPED, Directive(focus=["aiko"]))
        assert len(context.memories) < 40
        assert context.estimated_chars >= 4000
        assert context.dropped, "the assembler must report what the budget removed"

    async def test_the_players_pattern_is_interpreted_by_the_lead_character(
        self, world, session
    ):
        memory, assembler = self.assembler()
        for index in range(6):
            session.behavior.observe("empathy", 1.0, step_id=f"b{index}")
        session.characters["aiko"].relationship.update(affection=10, trust=10)
        context = await assembler.assemble(
            session, INTENT, TYPED, Directive(focus=["aiko"]),
        )
        assert "uncharitably" in context.behavior_note


class TestTraceCostAndReference:
    async def test_provider_tokens_reach_the_trace(self, world, tmp_path):
        from app.llm.base import record_usage
        from test_llm_path import step as llm_step, choice_step

        class UsageChat:
            name = "usage-stub"
            model = "stub-model"

            async def complete_json(self, **kwargs):
                record_usage({"prompt_tokens": 120, "completion_tokens": 80,
                              "total_tokens": 200})
                return {"summary": "Aiko listens.", "steps": [llm_step(), choice_step()]}

        bench = Bench(world, tmp_path, chat=UsageChat())
        await bench.start(world)
        await bench.generation.submit("g1", INTENT, decision=TYPED)
        await bench.generation.drain()

        trace = (await bench.traces.for_game("g1"))[0]
        assert (trace.prompt_tokens, trace.completion_tokens, trace.total_tokens) == (
            120, 80, 200,
        )
        assert trace.model == "stub-model"
        await bench.generation.shutdown()

    async def test_a_memory_used_by_a_real_generation_is_marked_referenced(
        self, world, tmp_path
    ):
        from app.domain.story import MemoryProposal
        from test_llm_path import step as llm_step, choice_step

        chat = StubChat({"summary": "Aiko listens.", "steps": [llm_step(), choice_step()]})
        bench = Bench(world, tmp_path, chat=chat)
        await bench.start(world)
        await bench.memory.remember(
            "g1", MemoryProposal(character="aiko", text="Kai borrowed her eraser."),
            step_index=0,
        )
        await bench.generation.submit("g1", INTENT, decision=TYPED)
        await bench.generation.drain()

        stored = await bench.memories.for_game("g1")
        assert stored[0].last_referenced_step == 0
        await bench.generation.shutdown()


class TestQualityOnTheBatch:
    async def test_the_quality_report_is_persisted_with_the_batch(self, world, tmp_path):
        chat = StubChat({"summary": "Aiko listens.", "steps": [llm_step(), choice_step()]})
        bench = Bench(world, tmp_path, chat=chat, quality=True)
        await bench.start(world)
        await bench.generation.submit("g1", INTENT, decision=TYPED)
        await bench.generation.drain()

        session = await bench.games.get("g1")
        assert session.pending.quality is not None
        assert session.pending.quality.overall_score > 0
        assert session.pending.trace_id

        trace = (await bench.traces.for_game("g1"))[0]
        assert trace.id == session.pending.trace_id
        assert trace.quality["overall_score"] == session.pending.quality.overall_score
        await bench.generation.shutdown()

    async def test_quality_cannot_override_the_validator(self, world, tmp_path, monkeypatch):
        chat = StubChat({"summary": "Aiko listens.", "steps": [llm_step(), choice_step()]})
        bench = Bench(world, tmp_path, chat=chat, quality=True)
        await bench.start(world)

        # Force a repair that ignores the player's agency; the Validator must remove it
        # and, with nothing left, the validated original must be committed instead.
        monkeypatch.setattr(
            bench.narrative, "_repair_steps",
            lambda steps, report: [GeneratedStep(
                type="narration", location="classroom", characters=["aiko"],
                narration="You confess your love.",
            )],
        )
        monkeypatch.setattr(
            NarrativeQualityEvaluator, "should_repair", lambda self, report: True
        )
        await bench.generation.submit("g1", INTENT, decision=TYPED)
        await bench.generation.drain()

        session = await bench.games.get("g1")
        assert session.steps, "a failed repair discarded the validated run"
        assert session.pending.status.value == "ready"
        assert any(step.is_blocking for step in session.steps)
        assert all("You confess" not in (step.narration or "") for step in session.steps)
        await bench.generation.shutdown()
