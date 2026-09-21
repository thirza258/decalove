"""Writing assistance preserves author context and validates before offering a draft."""

import asyncio
import json
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.llm.base import LLMError
from app.models.writing import StoryboardRequest, WritingRequest
from app.services.writing_service import WritingService


def scene(count=50):
    return {"summary": "A conversation about the unopened letter.", "blocks": [
        {"kind": "narration", "text": "Rain caught on the windowsill.", "speaker": ""},
        *[{"kind": "dialogue", "text": f"Spoken turn {i + 1}.", "speaker": "Mara" if i % 2 else "Jules"}
          for i in range(count)],
    ]}


def board(count=8):
    return {"summary": "Eight frames from the rooftop scene.", "panels": [
        {"shot": "wide" if index else "establishing", "title": f"Panel {index + 1}",
         "description": "Wet tiles, one open door.", "dialogue": "", "notes": ""} for index in range(count)]}


class Provider:
    name = "test-writer"

    def __init__(self, payload=None, error=None):
        self.payload = payload if payload is not None else scene()
        self.error = error
        self.calls = []

    async def complete_json(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.payload


async def test_default_is_fifty_dialogue_lines_with_narration_and_exact_author_context():
    provider = Provider()
    request = WritingRequest(
        format="novel", theme="Can you trust someone twice?", premise="A train station at midnight.",
        characters="Mara does not know Jules sold the house.", reference="  Previous chapter: the seal is UNBROKEN.\n",
        prompt='  Keep my exact phrase: "still here".\nNo reconciliation yet.  ',
        blocks=[{"kind": "dialogue", "text": "  You kept the letter?  ", "speaker": "Mara"}],
    )
    original = request.model_dump()
    result = await WritingService([provider]).assist(request)
    assert sum(b.kind == "dialogue" for b in result.blocks) == 50
    assert any(b.kind == "narration" for b in result.blocks)
    assert request.model_dump() == original
    context = json.loads(provider.calls[0]["user"].split("AUTHOR CONTEXT (JSON):\n")[1])
    assert context == original
    assert "EXACTLY 50" in provider.calls[0]["user"]
    assert result.provider == "test-writer"


async def test_incomplete_generation_tries_alternate_with_identical_input():
    incomplete = Provider(scene(49))
    alternate = Provider()
    await WritingService([incomplete, alternate]).assist(WritingRequest(prompt="  Don't change the promise. "))
    assert len(incomplete.calls) == len(alternate.calls) == 1
    assert incomplete.calls[0] == alternate.calls[0]


@pytest.mark.parametrize("payload", [
    scene(51), {"summary": "Empty", "blocks": []},
    {"summary": "Whitespace", "blocks": [{"kind": "narration", "text": "  ", "speaker": ""}]},
    {"summary": "Not a manuscript", "blocks": [{"kind": "choice", "text": "Choose", "speaker": ""}]},
    {"summary": "Speaker mismatch", "blocks": [{"kind": "narration", "text": "Rain.", "speaker": "Mara"}]},
    {"summary": "No narration", "blocks": scene()["blocks"][1:]},
])
async def test_invalid_proposal_is_not_delivered(payload):
    with pytest.raises(LLMError, match="Retry"):
        await WritingService([Provider(payload)]).assist(WritingRequest())


async def test_narration_and_single_passage_rewrite_contracts():
    narration = {"summary": "Ground the scene", "blocks": [scene()["blocks"][0]]}
    result = await WritingService([Provider(narration)]).assist(WritingRequest(action="narrate"))
    assert len(result.blocks) == 1
    rewrite = {"summary": "More subtext", "blocks": [
        {"kind": "dialogue", "text": "Is the kettle still warm?", "speaker": "Mara"},
    ]}
    request = WritingRequest(action="rewrite", selected_index=1, blocks=[
        {"kind": "narration", "text": "The room was cold.", "speaker": ""},
        {"kind": "dialogue", "text": "Can I stay?", "speaker": "Mara"},
    ])
    result = await WritingService([Provider(rewrite)]).assist(request)
    assert result.blocks[0].speaker == "Mara"
    rewrite["blocks"][0]["speaker"] = "Jules"
    with pytest.raises(LLMError):
        await WritingService([Provider(rewrite)]).assist(request)


async def test_provider_timeout_fails_over_and_cancellation_propagates():
    started = asyncio.Event()
    cancelled = asyncio.Event()

    class Hanging:
        name = "hanging"

        async def complete_json(self, **kwargs):
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

    alternate = Provider()
    service = WritingService([Hanging(), alternate], attempt_timeout_s=0.01)
    result = await asyncio.wait_for(service.assist(WritingRequest()), 0.5)
    assert result.blocks and cancelled.is_set()
    started.clear()
    cancelled.clear()
    alternate.calls.clear()
    service.attempt_timeout_s = 1
    task = asyncio.create_task(service.assist(WritingRequest()))
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert cancelled.is_set()
    assert not alternate.calls


async def test_total_deadline_bounds_all_providers():
    class Slow:
        name = "slow"

        async def complete_json(self, **kwargs):
            await asyncio.sleep(10)

    with pytest.raises(LLMError):
        await asyncio.wait_for(WritingService([Slow()] * 10, total_timeout_s=0.02).assist(WritingRequest()), 0.5)


async def test_http_disconnect_cancels_the_pending_writer():
    from fastapi import HTTPException
    from app.routes.writing import assist

    started = asyncio.Event()
    cancelled = asyncio.Event()

    class PendingWriter:
        async def assist(self, request):
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                cancelled.set()

    class DisconnectedRequest:
        async def is_disconnected(self):
            await started.wait()
            return True

    with pytest.raises(HTTPException) as failure:
        await assist(WritingRequest(), DisconnectedRequest(), SimpleNamespace(writing=PendingWriter()))
    assert failure.value.status_code == 499
    assert cancelled.is_set()


@pytest.mark.parametrize("patch", [
    {"dialogue_count": 0}, {"dialogue_count": 101}, {"dialogue_count": 1.5},
    {"prompt": "x" * 4001}, {"reference": "x" * 30001},
    {"selected_index": 0}, {"action": "rewrite"},
    {"action": "rewrite", "selected_index": 0, "blocks": [{"kind": "narration", "text": " "}]},
    {"blocks": [{"kind": "narration", "text": "x" * 12000}] * 11},
])
def test_requests_are_bounded_and_selections_must_exist(patch):
    with pytest.raises(ValidationError):
        WritingRequest(**patch)


def test_writing_routes_do_not_need_a_game_or_mutate_game_storage(client):
    assert client.get("/api/v1/writing/status").json() == {
        "available": False, "default_dialogue_count": 50, "default_panel_count": 8}
    offline = client.post("/api/v1/writing/assist", json={})
    assert offline.status_code == 503
    assert "not configured" in offline.json()["detail"]
    before = client.get("/api/v1/games").json()
    client.app.state.runtime.writing.providers = [Provider()]
    assert client.get("/api/v1/writing/status").json()["available"] is True
    response = client.post("/api/v1/writing/assist", json={"prompt": "Write a quiet reunion."})
    assert response.status_code == 200
    assert len(response.json()["blocks"]) == 51
    assert client.get("/api/v1/games").json() == before
    assert client.post("/api/v1/writing/assist", json={"dialogue_count": 1000}).status_code == 422


async def test_storyboard_asks_for_an_exact_shot_list_and_fails_over_with_identical_input():
    incomplete = Provider(board(7))
    alternate = Provider(board())
    request = StoryboardRequest(panel_count=8, premise="A rooftop at dusk.",
                                blocks=[{"kind": "narration", "text": "The city went quiet."}])
    original = request.model_dump()
    result = await WritingService([incomplete, alternate]).storyboard(request)
    assert [panel.shot for panel in result.panels][:2] == ["establishing", "wide"]
    assert len(result.panels) == 8
    assert result.provider == "test-writer"
    # The second attempt is the first request, unchanged, including the author's draft.
    assert incomplete.calls[0]["user"] == alternate.calls[0]["user"]
    assert "EXACTLY 8 panels" in alternate.calls[0]["user"]
    assert json.loads(alternate.calls[0]["user"].split("AUTHOR CONTEXT (JSON):\n")[1]) == original
    assert request.model_dump() == original


@pytest.mark.parametrize("payload", [
    {"summary": "Frames.", "panels": []},
    {"summary": "Frames.", "panels": [{"shot": "wide", "description": " "}] * 4},
    {"summary": " ", "panels": [{"shot": "wide", "description": "A door."}] * 4},
])
async def test_invalid_storyboards_are_not_delivered(payload):
    with pytest.raises(LLMError):
        await WritingService([Provider(payload)]).storyboard(StoryboardRequest(panel_count=4))


async def test_an_illustration_is_context_for_a_proposal_and_never_part_of_one():
    illustrated = [{"kind": "image", "text": "Wet rooftops at dusk", "speaker": ""},
                   {"kind": "narration", "text": "The city went quiet.", "speaker": ""}]
    provider = Provider({"summary": "Two paragraphs.", "blocks": [{"kind": "narration", "text": "Rain again.", "speaker": ""}]})
    await WritingService([provider]).assist(WritingRequest(action="narrate", blocks=illustrated))
    # The picture keeps its place in the draft, so passage numbers still line up.
    context = json.loads(provider.calls[0]["user"].split("AUTHOR CONTEXT (JSON):\n")[1])
    assert [block["kind"] for block in context["blocks"]] == ["image", "narration"]

    proposed = Provider({"summary": "A picture.", "blocks": [{"kind": "image", "text": "A photograph", "speaker": ""}]})
    with pytest.raises(LLMError):
        await WritingService([proposed]).assist(WritingRequest(action="narrate", blocks=illustrated))

    # Rewriting an illustration is refused before any provider is asked.
    with pytest.raises(ValidationError):
        WritingRequest(action="rewrite", selected_index=0, blocks=illustrated)


def test_storyboard_route_proposes_panels_without_touching_a_game(client):
    client.app.state.runtime.writing.providers = [Provider(board(4))]
    before = client.get("/api/v1/games").json()
    response = client.post("/api/v1/writing/storyboard", json={"panel_count": 4, "prompt": "The rooftop scene."})
    assert response.status_code == 200
    assert len(response.json()["panels"]) == 4
    assert response.json()["provider"] == "test-writer"
    assert client.get("/api/v1/games").json() == before
    assert client.post("/api/v1/writing/storyboard", json={"panel_count": 99}).status_code == 422
