"""OpenRouter-backed providers.

Chat uses ``response_format: json_schema`` with ``strict: true``. Support for that varies
by model *and* by the provider actually routed to, so ``provider.require_parameters`` is
set to keep the request off endpoints that would silently ignore it. Even then the JSON is
re-validated locally and one repair round-trip is attempted -- PRD §9.6 requires the
Validation Agent regardless of what the API promises.
"""

from __future__ import annotations

import asyncio
import base64
import binascii
import json
import logging
import re
from typing import Any

import httpx

from app.llm.base import ImageError, LLMError

log = logging.getLogger(__name__)

_RETRYABLE_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}


def _unfence(text: str) -> str:
    stripped = text.strip()
    if "```" in stripped:
        match = re.search(r"```(?:json)?\s*([\s\S]*?)(?:```|$)", stripped, re.IGNORECASE)
        if match:
            return match.group(1).strip()
    return stripped


def _repair_json(raw: str) -> dict[str, Any]:
    text = _unfence(raw)

    # 1. Extract outermost JSON object if preamble or postamble text exists
    start_idx = text.find("{")
    end_idx = text.rfind("}")
    if start_idx != -1:
        if end_idx != -1 and end_idx > start_idx:
            candidate = text[start_idx : end_idx + 1]
        else:
            candidate = text[start_idx:]
    else:
        candidate = text

    # Direct parse attempt
    try:
        val = json.loads(candidate)
        if isinstance(val, dict):
            return val
    except json.JSONDecodeError:
        pass

    # 2. Fix trailing commas before } or ]
    cleaned = re.sub(r",\s*([}\]])", r"\1", candidate)
    try:
        val = json.loads(cleaned)
        if isinstance(val, dict):
            return val
    except json.JSONDecodeError:
        pass

    # 3. Handle truncated JSON cut off inside a "steps" array
    steps_match = re.search(r'"steps"\s*:\s*\[', cleaned)
    if steps_match:
        last_step_end = -1
        depth = 0
        in_string = False
        escape = False
        array_start = steps_match.end() - 1

        for i in range(array_start, len(cleaned)):
            char = cleaned[i]
            if escape:
                escape = False
                continue
            if char == '\\':
                escape = True
                continue
            if char == '"':
                in_string = not in_string
                continue
            if not in_string:
                if char == '{':
                    depth += 1
                elif char == '}':
                    depth -= 1
                    if depth == 1:
                        last_step_end = i

        if last_step_end != -1:
            truncated = cleaned[: last_step_end + 1]
            truncated = re.sub(r",\s*$", "", truncated)
            truncated += "\n  ]\n}"
            try:
                val = json.loads(truncated)
                if isinstance(val, dict) and "steps" in val:
                    return val
            except json.JSONDecodeError:
                pass

    # 4. Bracket stack auto-closer for truncated objects
    stack: list[str] = []
    in_str = False
    esc = False
    for char in cleaned:
        if esc:
            esc = False
            continue
        if char == '\\':
            esc = True
            continue
        if char == '"':
            in_str = not in_str
            continue
        if not in_str:
            if char in ('{', '['):
                stack.append(char)
            elif char == '}' and stack and stack[-1] == '{':
                stack.pop()
            elif char == ']' and stack and stack[-1] == '[':
                stack.pop()

    if stack:
        auto_fixed = cleaned
        if in_str:
            auto_fixed += '"'
        auto_fixed = re.sub(r",\s*$", "", auto_fixed)
        for item in reversed(stack):
            auto_fixed += '}' if item == '{' else ']'
        try:
            val = json.loads(auto_fixed)
            if isinstance(val, dict):
                return val
        except json.JSONDecodeError:
            pass

    # Re-parse candidate directly to raise a clear LLMError with line details
    val = json.loads(candidate)
    if not isinstance(val, dict):
        raise ValueError(f"expected JSON object, got {type(val).__name__}")
    return val


class _OpenRouterBase:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        timeout: float,
        max_retries: int,
        referer: str = "",
        title: str = "",
    ) -> None:
        if not api_key:
            raise ValueError("OpenRouter provider requires an API key")
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._max_retries = max(0, max_retries)
        self._referer = referer
        self._title = title
        self._client: httpx.AsyncClient | None = None

    def _headers(self) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        if self._referer:
            headers["HTTP-Referer"] = self._referer
        if self._title:
            headers["X-Title"] = self._title
        return headers

    async def _http(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self._timeout)
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _post(self, path: str, payload: dict[str, Any], error: type[Exception]) -> dict[str, Any]:
        client = await self._http()
        url = f"{self._base_url}{path}"
        last: Exception | None = None

        for attempt in range(self._max_retries + 1):
            try:
                response = await client.post(url, json=payload, headers=self._headers())
            except httpx.HTTPError as exc:  # network/timeout
                last = error(f"{path} transport error: {exc}")
            else:
                if response.status_code < 400:
                    try:
                        return response.json()
                    except ValueError as exc:
                        raise error(f"{path} returned non-JSON body: {exc}") from exc
                body = response.text[:400]
                message = f"{path} failed with HTTP {response.status_code}: {body}"
                if response.status_code not in _RETRYABLE_STATUS:
                    raise error(message)
                last = error(message)

            if attempt < self._max_retries:
                delay = min(8.0, 0.75 * (2**attempt))
                log.warning("OpenRouter %s retry %d/%d: %s", path, attempt + 1, self._max_retries, last)
                await asyncio.sleep(delay)

        raise last or error(f"{path} failed")


class OpenRouterChat(_OpenRouterBase):
    name = "openrouter"

    def __init__(self, *, model: str, require_parameters: bool = True, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._model = model
        self._require_parameters = require_parameters

    async def complete_json(
        self,
        *,
        system: str,
        user: str,
        schema_name: str,
        schema: dict[str, Any],
        max_tokens: int = 12000,
        temperature: float = 0.8,
    ) -> dict[str, Any]:
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "response_format": {
                "type": "json_schema",
                "json_schema": {"name": schema_name, "strict": True, "schema": schema},
            },
        }
        if self._require_parameters:
            payload["provider"] = {"require_parameters": True}

        raw = await self._complete_text(payload)
        try:
            return self._parse(raw)
        except LLMError as first_error:
            # One repair round-trip: hand the model its own broken output and the error.
            log.warning("OpenRouter returned unparseable JSON, attempting repair: %s", first_error)
            # A fresh dict, not a mutation: the original payload stays a faithful record
            # of the first attempt, which matters when these are logged or traced.
            repair_payload = {
                **payload,
                "messages": messages
                + [
                    {"role": "assistant", "content": raw[:32000]},
                    {
                        "role": "user",
                        "content": (
                            "That response was not valid JSON for the required schema "
                            f"({first_error}). Reply with the corrected JSON object only."
                        ),
                    },
                ],
                "temperature": 0.2,
            }
            repaired = await self._complete_text(repair_payload)
            return self._parse(repaired)

    async def _complete_text(self, payload: dict[str, Any]) -> str:
        data = await self._post("/chat/completions", payload, LLMError)
        if data.get("error"):
            raise LLMError(f"OpenRouter error: {data['error']}")
        try:
            choice = data["choices"][0]
        except (KeyError, IndexError) as exc:
            raise LLMError(f"OpenRouter response had no choices: {str(data)[:300]}") from exc
        content = (choice.get("message") or {}).get("content")
        if isinstance(content, list):  # some providers return content parts
            content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
        if not content:
            finish = choice.get("finish_reason")
            raise LLMError(f"OpenRouter returned empty content (finish_reason={finish})")
        return content

    @staticmethod
    def _parse(raw: str) -> dict[str, Any]:
        try:
            value = _repair_json(raw)
        except Exception as exc:
            raise LLMError(f"model did not return JSON: {exc}") from exc
        if not isinstance(value, dict):
            raise LLMError(f"model returned {type(value).__name__}, expected a JSON object")
        return value


class OpenRouterImage(_OpenRouterBase):
    """Image generation via OpenRouter's unified image endpoint.

    ``POST /images`` with ``{"model", "prompt"}`` returns
    ``{"data": [{"b64_json": ..., "media_type": ...}]}``.
    """

    name = "openrouter-image"

    def __init__(self, *, model: str, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._model = model

    async def generate(self, prompt: str, *, width: int = 1024, height: int = 576) -> tuple[bytes, str]:
        data = await self._post("/images", {"model": self._model, "prompt": prompt}, ImageError)
        if data.get("error"):
            raise ImageError(f"OpenRouter image error: {data['error']}")
        items = data.get("data") or []
        if not items:
            raise ImageError(f"image response contained no data: {str(data)[:300]}")

        first = items[0]
        encoded = first.get("b64_json")
        if not encoded:
            # Some routes return a URL or a data: URL instead of raw base64.
            url = first.get("url") or (first.get("image_url") or {}).get("url")
            if not url:
                raise ImageError(f"image response had neither b64_json nor url: {str(first)[:300]}")
            if url.startswith("data:"):
                header, _, encoded = url.partition(",")
                media = header[5:].split(";")[0] or "image/png"
                return base64.b64decode(encoded), media
            client = await self._http()
            fetched = await client.get(url)
            fetched.raise_for_status()
            return fetched.content, fetched.headers.get("content-type", "image/png")

        try:
            return base64.b64decode(encoded), first.get("media_type") or "image/png"
        except (binascii.Error, ValueError) as exc:
            raise ImageError(f"image data was not valid base64: {exc}") from exc
