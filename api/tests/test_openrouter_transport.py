"""HTTP-level coverage for the OpenRouter providers.

``complete_json`` is tested elsewhere with a stub provider, which skips everything
between the agent and the wire: headers, the request body, retry policy, and the
image response decoding. Those are the parts that fail against a real endpoint,
so they get a real ``httpx`` transport -- just a fake one.
"""

from __future__ import annotations

import base64
import json

import httpx
import pytest

from app.llm import openrouter as module
from app.llm.base import ImageError, LLMError
from app.llm.openrouter import OpenRouterChat, OpenRouterImage


@pytest.fixture(autouse=True)
def no_backoff(monkeypatch):
    async def instant(_seconds):
        return None

    monkeypatch.setattr(module.asyncio, "sleep", instant)


def wire(monkeypatch, handler):
    """Route every AsyncClient this module builds through a mock transport."""
    recorded: list[httpx.Request] = []

    def capture(request: httpx.Request) -> httpx.Response:
        recorded.append(request)
        return handler(request, len(recorded))

    real = httpx.AsyncClient
    transport = httpx.MockTransport(capture)
    monkeypatch.setattr(
        module.httpx, "AsyncClient", lambda **kwargs: real(transport=transport, **kwargs)
    )
    return recorded


def completion(payload: dict) -> httpx.Response:
    return httpx.Response(
        200, json={"choices": [{"message": {"content": json.dumps(payload)}}]}
    )


def chat(**overrides) -> OpenRouterChat:
    settings = {
        "model": "google/gemini-3.7-flash",
        "api_key": "sk-test",
        "base_url": "https://openrouter.ai/api/v1",
        "timeout": 5,
        "max_retries": 2,
        "referer": "https://decalove.example",
        "title": "Decalove",
    }
    settings.update(overrides)
    return OpenRouterChat(**settings)


class TestRequestShape:
    async def test_the_request_carries_auth_attribution_and_the_strict_schema(self, monkeypatch):
        recorded = wire(monkeypatch, lambda request, n: completion({"ok": True}))

        schema = {"type": "object", "properties": {}, "required": [], "additionalProperties": False}
        result = await chat().complete_json(
            system="you are the director", user="what happens next", schema_name="story_run", schema=schema
        )
        assert result == {"ok": True}

        request = recorded[0]
        assert str(request.url) == "https://openrouter.ai/api/v1/chat/completions"
        assert request.headers["Authorization"] == "Bearer sk-test"
        assert request.headers["HTTP-Referer"] == "https://decalove.example"
        assert request.headers["X-Title"] == "Decalove"

        body = json.loads(request.content)
        assert body["model"] == "google/gemini-3.7-flash"
        assert [m["role"] for m in body["messages"]] == ["system", "user"]
        assert body["response_format"]["type"] == "json_schema"
        assert body["response_format"]["json_schema"]["strict"] is True
        assert body["response_format"]["json_schema"]["schema"] == schema
        # Keeps the request off provider endpoints that would ignore response_format.
        assert body["provider"] == {"require_parameters": True}

    async def test_require_parameters_can_be_turned_off(self, monkeypatch):
        recorded = wire(monkeypatch, lambda request, n: completion({}))
        await chat(require_parameters=False).complete_json(
            system="s", user="u", schema_name="n", schema={}
        )
        assert "provider" not in json.loads(recorded[0].content)

    async def test_unparseable_json_attempts_repair(self, monkeypatch):
        attempts = 0

        def handler(request, n):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                return httpx.Response(200, json={"choices": [{"message": {"content": "not-json"}}]})
            return completion({"ok": True, "repaired": True})

        wire(monkeypatch, handler)
        result = await chat().complete_json(
            system="s", user="u", schema_name="n", schema={}
        )
        assert result == {"ok": True, "repaired": True}
        assert attempts == 2

    async def test_json_repair_handles_trailing_commas_and_fences(self, monkeypatch):
        broken_json = """Here is the output:
```json
{
  "title": "Decalove",
  "steps": [
    {"index": 0, "narration": "Hello world",},
  ],
}
```
"""
        wire(monkeypatch, lambda request, n: httpx.Response(
            200, json={"choices": [{"message": {"content": broken_json}}]}
        ))
        result = await chat().complete_json(
            system="s", user="u", schema_name="n", schema={}
        )
        assert result["title"] == "Decalove"
        assert len(result["steps"]) == 1

    async def test_json_repair_handles_truncated_steps_array(self, monkeypatch):
        truncated_json = """{
  "title": "Decalove",
  "steps": [
    {"index": 0, "narration": "First step"},
    {"index": 1, "narration": "Second step"},
    {"index": 2, "narration": "Incomplete
"""
        wire(monkeypatch, lambda request, n: httpx.Response(
            200, json={"choices": [{"message": {"content": truncated_json}}]}
        ))
        result = await chat().complete_json(
            system="s", user="u", schema_name="n", schema={}
        )
        assert result["title"] == "Decalove"
        assert len(result["steps"]) == 2

    async def test_content_returned_as_parts_is_reassembled(self, monkeypatch):
        def handler(request, n):
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": [{"text": '{"a":'}, {"text": " 1}"}]}}]},
            )

        wire(monkeypatch, handler)
        assert await chat().complete_json(system="s", user="u", schema_name="n", schema={}) == {"a": 1}


class TestRetryPolicy:
    async def test_a_rate_limit_is_retried_then_succeeds(self, monkeypatch):
        def handler(request, n):
            return httpx.Response(429, text="slow down") if n == 1 else completion({"ok": 1})

        recorded = wire(monkeypatch, handler)
        assert await chat().complete_json(system="s", user="u", schema_name="n", schema={}) == {"ok": 1}
        assert len(recorded) == 2

    async def test_a_bad_request_is_not_retried(self, monkeypatch):
        recorded = wire(monkeypatch, lambda request, n: httpx.Response(400, text="unsupported model"))

        with pytest.raises(LLMError, match="400"):
            await chat().complete_json(system="s", user="u", schema_name="n", schema={})
        assert len(recorded) == 1, "a 400 will not become a 200 by asking again"

    async def test_retries_are_bounded(self, monkeypatch):
        recorded = wire(monkeypatch, lambda request, n: httpx.Response(503, text="down"))

        with pytest.raises(LLMError):
            await chat(max_retries=2).complete_json(system="s", user="u", schema_name="n", schema={})
        assert len(recorded) == 3

    async def test_an_error_body_with_a_200_is_still_an_error(self, monkeypatch):
        wire(monkeypatch, lambda request, n: httpx.Response(200, json={"error": {"message": "no credits"}}))

        with pytest.raises(LLMError, match="no credits"):
            await chat().complete_json(system="s", user="u", schema_name="n", schema={})

    async def test_an_empty_completion_is_an_error_not_a_crash(self, monkeypatch):
        wire(
            monkeypatch,
            lambda request, n: httpx.Response(
                200, json={"choices": [{"message": {"content": ""}, "finish_reason": "length"}]}
            ),
        )
        with pytest.raises(LLMError, match="length"):
            await chat().complete_json(system="s", user="u", schema_name="n", schema={})


class TestImageProvider:
    def image(self, **overrides) -> OpenRouterImage:
        settings = {
            "model": "google/gemini-3.1-flash-image",
            "api_key": "sk-test",
            "base_url": "https://openrouter.ai/api/v1",
            "timeout": 5,
            "max_retries": 0,
        }
        settings.update(overrides)
        return OpenRouterImage(**settings)

    async def test_base64_payloads_are_decoded(self, monkeypatch):
        payload = base64.b64encode(b"\x89PNG fake").decode()
        recorded = wire(
            monkeypatch,
            lambda request, n: httpx.Response(
                200, json={"data": [{"b64_json": payload, "media_type": "image/png"}]}
            ),
        )

        data, content_type = await self.image().generate("aiko on the rooftop at sunset")
        assert data == b"\x89PNG fake"
        assert content_type == "image/png"

        request = recorded[0]
        assert str(request.url).endswith("/images")
        assert json.loads(request.content) == {
            "model": "google/gemini-3.1-flash-image",
            "prompt": "aiko on the rooftop at sunset",
        }

    async def test_a_data_url_response_is_decoded(self, monkeypatch):
        payload = base64.b64encode(b"jpegbytes").decode()
        wire(
            monkeypatch,
            lambda request, n: httpx.Response(
                200, json={"data": [{"url": f"data:image/jpeg;base64,{payload}"}]}
            ),
        )
        data, content_type = await self.image().generate("x")
        assert (data, content_type) == (b"jpegbytes", "image/jpeg")

    async def test_an_empty_data_array_raises_rather_than_returning_nothing(self, monkeypatch):
        wire(monkeypatch, lambda request, n: httpx.Response(200, json={"data": []}))
        with pytest.raises(ImageError):
            await self.image().generate("x")

    async def test_image_failure_never_takes_the_game_down(self, monkeypatch, tmp_path):
        """PRD §26: a failed image degrades to a placeholder, not to an exception."""
        from app.assets.local_store import LocalAssetStore
        from app.agents.visual import AssetSpec
        from app.domain.enums import AssetStatus
        from app.repositories.memory_repo import InMemoryAssetRepository
        from app.services.asset_service import AssetService

        wire(monkeypatch, lambda request, n: httpx.Response(500, text="model exploded"))

        service = AssetService(
            InMemoryAssetRepository(), LocalAssetStore(tmp_path), self.image(), enabled=True
        )
        ref = await service.ensure(AssetSpec(kind="background", cache_key="bg_x", prompt="p"), "w")
        assert ref.status is AssetStatus.unavailable
