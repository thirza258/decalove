"""Web story recovery: model failover, worker lifecycle, retry and cursor replay."""
import asyncio
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest

from app.agents.narrative import NarrativeAgent
from app.agents.scripted import ScriptedNarrator
from app.config import Settings
from app.domain.enums import BatchStatus
from app.domain.state import PlayerProfile
from app.llm.base import LLMError
from app.repositories.base import StaleSessionError
from app.runtime import build_runtime
from test_generation_service import Engine, INTENT, TYPED
from test_llm_path import StubChat, choice_step, step

PAYLOAD = {"summary": "The conversation continues.", "steps": [step(), choice_step()]}


@pytest.mark.parametrize("failure", [LLMError("network down"), ValueError("bad JSON"), RuntimeError("provider crashed")])
async def test_web_tries_next_ai_with_the_same_story_context(world, validator, session, failure):
    primary = StubChat(error=failure)
    fallback = StubChat(PAYLOAD)
    agent = NarrativeAgent(world, validator, ScriptedNarrator(world), chat=primary,
                           web_mode=True, fallback_chats=[fallback])
    result = await agent.generate(session, INTENT, [])
    assert result.ok and result.used_fallback
    assert primary.calls[0] == fallback.calls[0]
    assert result.summary == PAYLOAD["summary"]


@pytest.mark.parametrize("payload", [{"unexpected": True}, {"steps": [], "summary": ""}])
async def test_invalid_story_tries_another_ai(world, validator, session, payload):
    fallback = StubChat(PAYLOAD)
    agent = NarrativeAgent(world, validator, ScriptedNarrator(world), chat=StubChat(payload),
                           web_mode=True, fallback_chats=[fallback])
    assert (await agent.generate(session, INTENT, [])).used_fallback
    assert len(fallback.calls) == 1


async def test_hung_primary_leaves_time_for_fallback(world, validator, session):
    class HangingChat:
        name = "hanging"
        async def complete_json(self, **kwargs):
            await asyncio.sleep(60)
    fallback = StubChat(PAYLOAD)
    agent = NarrativeAgent(world, validator, ScriptedNarrator(world), chat=HangingChat(),
                           web_mode=True, fallback_chats=[fallback], attempt_timeout_s=0.01)
    result = await asyncio.wait_for(agent.generate(session, INTENT, []), timeout=1)
    assert result.ok and result.used_fallback


async def test_cancellation_does_not_start_fallback(world, validator, session):
    primary = StubChat(error=asyncio.CancelledError())
    fallback = StubChat(PAYLOAD)
    agent = NarrativeAgent(world, validator, ScriptedNarrator(world), chat=primary,
                           web_mode=True, fallback_chats=[fallback])
    with pytest.raises(asyncio.CancelledError):
        await agent.generate(session, INTENT, [])
    assert not fallback.calls


async def test_all_ai_failures_are_terminal_and_retry_preserves_the_turn(world, tmp_path):
    broken = StubChat(error=LLMError("network down"))
    engine = Engine(world, tmp_path, chat=broken)
    engine.narrative.web_mode = True
    engine.narrative.fallback_chats = [StubChat(error=LLMError("also down"))]
    await engine.start(world)
    first = await engine.generation.submit("g1", INTENT, decision=TYPED)
    await engine.generation.drain()
    failed = await engine.games.get("g1")
    assert failed.pending.status is BatchStatus.failed
    assert not failed.steps
    for delivery in (engine.service.next_step, engine.service.next_batch):
        body = await delivery("g1")
        assert body.status == "failed" and body.batch_id == first.batch_id
    assert not engine.generation._tasks, "polling must not silently regenerate a failed turn"

    engine.narrative.chat = StubChat(PAYLOAD)
    retried = await engine.service.retry_generation("g1")
    assert retried.batch_id != first.batch_id
    await engine.generation.drain()
    recovered = await engine.games.get("g1")
    assert recovered.pending.status is BatchStatus.ready
    assert recovered.pending.intent == INTENT
    assert recovered.pending.decision == TYPED
    assert recovered.steps
    assert len(broken.calls) == 1


async def test_web_generation_timeout_is_failed_without_scripted_prose(world, tmp_path):
    engine = Engine(world, tmp_path)
    await engine.start(world)
    engine.narrative.web_mode = True
    engine.generation.timeout_s = 0.01
    async def hang(*args, **kwargs):
        await asyncio.sleep(60)
    engine.narrative.generate = hang
    await engine.generation.submit("g1", INTENT, decision=TYPED)
    await engine.generation.drain()
    session = await engine.games.get("g1")
    assert session.pending.status is BatchStatus.failed and not session.steps


async def test_a_lost_worker_expires_and_late_completion_cannot_overwrite_retry(world, tmp_path):
    engine = Engine(world, tmp_path, chat=StubChat(PAYLOAD))
    await engine.start(world)
    engine.narrative.web_mode = True
    engine.generation._spawn = lambda coro: coro.close()  # leave the job queued
    batch = await engine.generation.submit("g1", INTENT, decision=TYPED)
    session = await engine.games.get("g1")
    session.pending.created_at = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=10)
    await engine.games.save(session)
    assert (await engine.service.next_batch("g1")).status == "failed"
    retried = await engine.service.retry_generation("g1")
    result = await engine.narrative.generate(session, INTENT, [])
    await engine.generation.commit_run("g1", batch, result, INTENT)
    await engine.generation._mark_failed("g1", batch, "late failure")
    updated = await engine.games.get("g1")
    assert updated.pending.batch_id == retried.batch_id and not updated.steps
    assert updated.pending.status is BatchStatus.queued


async def test_duplicate_worker_and_commit_do_not_duplicate_story(world, tmp_path):
    engine = Engine(world, tmp_path, chat=StubChat(PAYLOAD))
    await engine.start(world)
    batch = await engine.generation.submit("g1", INTENT, decision=TYPED)
    await engine.generation.drain()
    session = await engine.games.get("g1")
    count = len(session.steps)
    await engine.generation._run_batch("g1", batch, INTENT, TYPED, session, None)
    result = await engine.narrative.generate(session, INTENT, [])
    await engine.generation.commit_run("g1", batch, result, INTENT)
    assert len((await engine.games.get("g1")).steps) == count
    assert len(engine.narrative.chat.calls) == 2


async def test_commit_retries_a_concurrent_api_write(world, tmp_path, monkeypatch):
    engine = Engine(world, tmp_path, chat=StubChat(PAYLOAD))
    await engine.start(world)
    original = engine.generation._commit
    calls = 0
    async def conflict_once(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            raise StaleSessionError("player advanced while the worker committed")
        return await original(*args, **kwargs)
    monkeypatch.setattr(engine.generation, "_commit", conflict_once)
    await engine.generation.submit("g1", INTENT, decision=TYPED)
    await engine.generation.drain()
    assert (await engine.games.get("g1")).pending.status is BatchStatus.ready
    assert len(engine.narrative.chat.calls) == 1, "commit retries must not regenerate prose"


async def test_web_delivery_replays_lost_response_and_waits_for_unanswered_choice(tmp_path):
    runtime = await build_runtime(Settings(_env_file=None, WEB_MODE=True,
        STORAGE_BACKEND="memory", ASSET_BACKEND="local", LOCAL_ASSET_DIR=str(tmp_path),
        OPENROUTER_API_KEY="", TASK_QUEUE_BACKEND="asyncio"))
    try:
        game = await runtime.game_service.create_game(PlayerProfile())
        first = await runtime.game_service.next_batch(game.id, after_index=-1)
        saved = await runtime.games.get(game.id)
        replay = await runtime.game_service.next_batch(game.id, after_index=-1)
        assert replay.steps == first.steps
        assert (await runtime.games.get(game.id)).characters == saved.characters
        assert (await runtime.game_service.next_batch(game.id)).status == "awaiting_player"
        assert not runtime.generation._tasks
    finally:
        await runtime.close()


async def test_celery_with_memory_storage_uses_in_process_generation(tmp_path):
    runtime = await build_runtime(Settings(_env_file=None, WEB_MODE=True,
        STORAGE_BACKEND="memory", TASK_QUEUE_BACKEND="celery", ASSET_BACKEND="local",
        LOCAL_ASSET_DIR=str(tmp_path), OPENROUTER_API_KEY=""))
    try:
        assert runtime.generation.task_backend == "asyncio"
    finally:
        await runtime.close()


async def test_lost_post_response_can_be_repeated_without_duplicate_history(world, tmp_path):
    engine = Engine(world, tmp_path, chat=StubChat(PAYLOAD))
    game = await engine.service.create_game(PlayerProfile())
    first = await engine.service.next_batch(game.id)
    decision = next(step for step in first.steps if step.is_blocking)
    batch, _ = await engine.service.submit_choice(game.id, decision.step_id,
        decision.next_choices[0].id, request_id="same-request")
    await engine.generation.drain()
    before = await engine.games.get(game.id)
    repeated, _ = await engine.service.submit_choice(game.id, decision.step_id,
        decision.next_choices[0].id, request_id="same-request")
    after = await engine.games.get(game.id)
    assert repeated.batch_id == batch.batch_id
    assert after.history == before.history and after.style == before.style


async def test_broker_outage_does_not_block_the_http_loop_and_runs_locally(world, tmp_path, monkeypatch):
    import time
    class BrokenBroker:
        @staticmethod
        def delay(**kwargs):
            time.sleep(0.1)
            raise ConnectionError("Redis unavailable")
    monkeypatch.setattr("app.tasks.generation_tasks.generate_batch_task", BrokenBroker)
    engine = Engine(world, tmp_path, chat=StubChat(PAYLOAD))
    await engine.start(world)
    engine.generation.task_backend = "celery"
    before = time.monotonic()
    await engine.generation.submit("g1", INTENT, decision=TYPED)
    assert time.monotonic() - before < 0.05
    await asyncio.sleep(0.01)
    assert time.monotonic() - before < 0.08, "broker publishing blocked unrelated requests"
    await engine.generation.drain()
    assert (await engine.games.get("g1")).pending.status is BatchStatus.ready


@pytest.mark.parametrize("fails", [False, True])
async def test_real_celery_task_reports_persisted_outcome(world, tmp_path, monkeypatch, fails):
    from types import SimpleNamespace
    from app.tasks.generation_tasks import generate_batch_task
    chat = StubChat(error=LLMError("offline")) if fails else StubChat(PAYLOAD)
    engine = Engine(world, tmp_path, chat=chat)
    await engine.start(world)
    engine.narrative.web_mode = True
    monkeypatch.setattr(engine.generation, "_spawn", lambda coro: coro.close())
    batch = await engine.generation.submit("g1", INTENT, decision=TYPED)
    runtime = SimpleNamespace(games=engine.games, generation=engine.generation,
                              storage_backend="mongo", close=AsyncMock())
    monkeypatch.setattr("app.tasks.generation_tasks.build_runtime", AsyncMock(return_value=runtime))
    payload = dict(game_id="g1", batch_id=batch.batch_id,
                   intent_dict=INTENT.model_dump(mode="json"), decision_dict=TYPED.model_dump(mode="json"))
    # Run the actual registered task, with its own event loop, like a worker process.
    outcome = await asyncio.to_thread(lambda: generate_batch_task.apply(kwargs=payload).get())
    assert outcome["status"] == ("failed" if fails else "ready")
    assert (await engine.games.get("g1")).pending.status.value == outcome["status"]
    duplicate = await asyncio.to_thread(lambda: generate_batch_task.apply(kwargs=payload).get())
    assert duplicate["status"] == "skipped"
    assert len(chat.calls) == 1


@pytest.mark.parametrize("parse_fails", [False, True])
async def test_custom_input_reaches_the_writer_with_exact_words_and_survives_retry(world, tmp_path, parse_fails):
    from app.domain.enums import StepType
    from app.domain.story import StoryStep

    text = "I ask her about the unfinished blue painting, and offer to help after school."
    class IntentThenUnavailableStory:
        name = "primary"
        calls = []
        async def complete_json(self, **kwargs):
            self.calls.append(kwargs)
            if kwargs["schema_name"] == "player_intent" and not parse_fails:
                return {"action": "help", "target": "aiko", "risk": "medium", "summary": "Kai offers to help Aiko finish her painting"}
            raise LLMError("primary offline")

    primary = IntentThenUnavailableStory()
    primary.calls = []
    fallback = StubChat(error=LLMError("fallback offline"))
    engine = Engine(world, tmp_path, chat=primary)
    engine.narrative.web_mode = True
    engine.narrative.fallback_chats = [fallback]
    engine.generation.director.chat = primary
    engine.service.director = engine.generation.director
    session = await engine.start(world)
    session.steps = [
        StoryStep(step_id="step_00000", index=0, batch_id="scene", type=StepType.dialogue,
                  location="classroom", characters=["aiko"],
                  dialogue={"speaker": "aiko", "text": "My blue painting still needs a background."}),
        StoryStep(step_id="step_00001", index=1, batch_id="scene", type=StepType.choice,
                  location="classroom", characters=["aiko"], narration="How do you respond?",
                  next_choices=[{"id": "leave", "text": "Leave the classroom."}]),
        StoryStep(step_id="step_00002", index=2, batch_id="scene", type=StepType.dialogue,
                  location="classroom", characters=["mika"],
                  dialogue={"speaker": "mika", "text": "This later conversation has not happened yet."}),
    ]
    session.cursor = 2  # Batch delivery includes the tail; the player is answering step 1.
    session.world.present_characters = ["mika"]
    await engine.games.save(session)
    accepted, _ = await engine.service.submit_action(session.id, text, "step_00001", request_id="custom-input")
    await engine.generation.drain()
    failed = await engine.games.get(session.id)
    assert failed.pending.status is BatchStatus.failed
    assert failed.pending.decision.typed == text
    assert failed.pending.decision.used_free_text_when_offered_choices is True
    assert failed.pending.refine_input == text
    intent_prompt = primary.calls[0]["user"]
    assert "My blue painting still needs a background." in intent_prompt
    assert "Leave the classroom." in intent_prompt
    assert "This later conversation has not happened yet." not in intent_prompt
    assert text in intent_prompt
    assert "PRESENT RIGHT NOW: aiko" in intent_prompt
    story_prompt = fallback.calls[0]["user"]
    assert text in story_prompt
    assert "honour its specifics" in story_prompt
    assert "menu did not contain" in story_prompt
    if not parse_fails:
        assert "Parsed as: action=help, target=aiko" in story_prompt

    fallback.error = None
    fallback.payloads = [PAYLOAD]
    await engine.service.retry_generation(session.id)
    await engine.generation.drain()
    ready = await engine.games.get(session.id)
    assert ready.pending.status is BatchStatus.ready
    assert ready.pending.batch_id != accepted.batch_id
    assert ready.pending.decision.typed == text
    assert ready.last_intent.raw == text
    assert ready.last_intent.target == "aiko", "a later buffered speaker must not steal the player's response"
    assert ready.style.typed == 1 and ready.style.chosen == 0
    assert sum(text in entry for entry in ready.history) == 1
    assert text in fallback.calls[-1]["user"]
