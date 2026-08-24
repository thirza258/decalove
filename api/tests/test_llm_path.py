"""Coverage for the branch that only runs when OPENROUTER_API_KEY is set.

Everything else in the suite exercises the offline seams, which means the code that
actually ships to players -- DTO parsing, the strict schema handed to the model, the
repair round-trip, and every fallback edge -- would otherwise never execute. A stub
provider closes that gap without a key or a network.
"""

from __future__ import annotations

import asyncio

import pytest

from app.agents.narrative import NarrativeAgent
from app.agents.scripted import ScriptedNarrator
from app.domain.intent import PlayerIntent
from app.llm.base import LLMError
from app.llm.openrouter import OpenRouterChat


class StubChat:
    """A ChatProvider that returns canned payloads and records what it was asked."""

    name = "stub"

    def __init__(self, *payloads, error: Exception | None = None) -> None:
        self.payloads = list(payloads)
        self.error = error
        self.calls: list[dict] = []

    async def complete_json(self, **kwargs):
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.payloads.pop(0) if len(self.payloads) > 1 else self.payloads[0]


def step(**overrides):
    base = {
        "type": "dialogue",
        "location": "classroom",
        "characters": ["aiko"],
        "narration": None,
        "dialogue": {"speaker": "aiko", "text": "You came back.", "emotion": "surprised"},
        "emotions": [{"character": "aiko", "emotion": "surprised"}],
        "relationship_changes": [{"character": "aiko", "affection": 2}],
        "flags_set": [],
        "memory": None,
        "next_choices": [],
        "visual": {"background": "classroom", "character": "aiko", "expression": "surprised"},
    }
    base.update(overrides)
    return base


def choice_step():
    return step(
        type="choice",
        dialogue=None,
        narration="She is waiting.",
        next_choices=[{"id": "a", "text": "I did."}, {"id": "b", "text": "Don't read into it."}],
    )


def agent_with(chat, world, validator):
    return NarrativeAgent(world, validator, ScriptedNarrator(world), chat=chat, max_steps=10)


INTENT = PlayerIntent(action="talk_to", target="aiko", raw="hello")


class TestHappyPath:
    async def test_model_output_becomes_engine_owned_steps(self, world, validator, session):
        chat = StubChat({"summary": "Aiko softened.", "steps": [step(), choice_step()]})
        result = await agent_with(chat, world, validator).generate(session, INTENT, [])

        assert result.used_fallback is False
        assert result.provider == "stub"
        assert result.summary == "Aiko softened."
        assert [s.type.value for s in result.steps] == ["dialogue", "choice"]
        assert result.steps[0].relationship_changes["aiko"].affection == 2
        assert result.steps[0].emotion == {"aiko": "surprised"}
        assert result.steps[-1].is_blocking

    async def test_the_model_is_handed_a_strict_schema(self, world, validator, session):
        chat = StubChat({"summary": "", "steps": [choice_step()]})
        await agent_with(chat, world, validator).generate(session, INTENT, [])

        schema = chat.calls[0]["schema"]
        assert schema["additionalProperties"] is False
        assert set(schema["required"]) == set(schema["properties"])
        assert chat.calls[0]["schema_name"] == "story_run"
        assert "PLAYER AGENCY" in chat.calls[0]["system"]

    async def test_the_prompt_carries_state_and_memories(self, world, validator, session):
        from app.domain.memory import MemoryRecord

        chat = StubChat({"summary": "", "steps": [choice_step()]})
        memory = MemoryRecord(
            id="m1", game_id=session.id, character="aiko", text="Player defended Aiko", importance=0.9
        )
        await agent_with(chat, world, validator).generate(session, INTENT, [memory])

        user = chat.calls[0]["user"]
        assert "Player defended Aiko" in user
        assert "classroom" in user
        assert "Kai" in user


class TestModelOutputIsNotTrusted:
    async def test_a_step_that_speaks_for_the_player_is_cut(self, world, validator, session):
        chat = StubChat(
            {
                "summary": "",
                "steps": [
                    step(),
                    step(dialogue={"speaker": "player", "text": "Yes, I promise.", "emotion": None}),
                    choice_step(),
                ],
            }
        )
        result = await agent_with(chat, world, validator).generate(session, INTENT, [])

        assert result.used_fallback is False
        assert all(
            not (s.dialogue and s.dialogue.speaker == "player") for s in result.steps
        )
        assert any(v.rule == "player_agency" for v in result.report.violations)
        assert result.steps[-1].is_blocking, "the run must still hand control back"

    async def test_oversized_deltas_from_the_model_are_clamped(self, world, validator, session):
        chat = StubChat(
            {
                "summary": "",
                "steps": [
                    step(relationship_changes=[{"character": "aiko", "affection": 90, "trust": 90}]),
                    choice_step(),
                ],
            }
        )
        result = await agent_with(chat, world, validator).generate(session, INTENT, [])
        delta = result.steps[0].relationship_changes["aiko"]
        assert (delta.affection, delta.trust) == (5, 5)


class TestFallback:
    async def test_provider_failure_falls_back_to_the_scripted_narrator(self, world, validator, session):
        chat = StubChat(error=LLMError("upstream 503"))
        result = await agent_with(chat, world, validator).generate(session, INTENT, [])

        assert result.used_fallback is True
        assert result.steps, "the player must still get a turn"
        assert result.steps[-1].is_blocking

    async def test_unusable_output_falls_back(self, world, validator, session):
        """Schema-valid but empty: nothing survives validation, so the story continues elsewhere."""
        chat = StubChat({"summary": "", "steps": []})
        result = await agent_with(chat, world, validator).generate(session, INTENT, [])

        assert result.used_fallback is True
        assert result.steps

    async def test_malformed_payload_falls_back(self, world, validator, session):
        chat = StubChat({"summary": "", "steps": [{"type": "not_a_real_type"}]})
        result = await agent_with(chat, world, validator).generate(session, INTENT, [])
        assert result.used_fallback is True
        assert result.steps


class TestRepairRoundTrip:
    async def test_unparseable_json_triggers_exactly_one_repair_attempt(self):
        class Flaky(OpenRouterChat):
            def __init__(self):
                super().__init__(model="m", api_key="k", base_url="http://x", timeout=1, max_retries=0)
                self.bodies = ["this is not json", '{"summary": "ok", "steps": []}']
                self.seen: list[dict] = []

            async def _complete_text(self, payload):
                self.seen.append(payload)
                return self.bodies.pop(0)

        chat = Flaky()
        result = await chat.complete_json(system="s", user="u", schema_name="story_run", schema={})

        assert result == {"summary": "ok", "steps": []}
        assert len(chat.seen) == 2, "should retry once, not loop"
        repair_turn = chat.seen[1]["messages"][-1]["content"]
        assert "not valid JSON" in repair_turn
        assert chat.seen[1]["temperature"] < chat.seen[0]["temperature"]

    async def test_a_second_failure_gives_up(self):
        class AlwaysBroken(OpenRouterChat):
            def __init__(self):
                super().__init__(model="m", api_key="k", base_url="http://x", timeout=1, max_retries=0)

            async def _complete_text(self, payload):
                return "still not json"

        with pytest.raises(LLMError):
            await AlwaysBroken().complete_json(system="s", user="u", schema_name="n", schema={})

    def test_an_api_key_is_required(self):
        with pytest.raises(ValueError):
            OpenRouterChat(model="m", api_key="", base_url="http://x", timeout=1, max_retries=0)


class TestDirectorLlmPath:
    async def test_llm_intent_is_normalised_against_the_cast(self, world, session):
        from app.agents.director import DirectorAgent

        chat = StubChat(
            {
                "action": "invite_character",
                "target": "Aiko",  # a display name, not an id
                "emotion": "nervous",
                "risk": "medium",
                "summary": "asks Aiko to walk home",
                "meaningful": True,
                "raw": "ignored",
            }
        )
        intent = await DirectorAgent(world, chat=chat).parse(session, "walk home with Aiko?")

        assert intent.target == "aiko"
        assert intent.raw == "walk home with Aiko?"
        assert chat.calls[0]["schema_name"] == "player_intent"

    async def test_a_failing_parse_falls_back_to_keywords(self, world, session):
        from app.agents.director import DirectorAgent

        chat = StubChat(error=LLMError("nope"))
        intent = await DirectorAgent(world, chat=chat).parse(session, "I apologise to Haruto")

        assert intent.action == "apologise"
        assert intent.target == "haruto"
