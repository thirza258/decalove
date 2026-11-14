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
import random
import re
import time
from typing import Any

import httpx

from app.llm.base import ImageError, LLMError, record_usage, reset_usage

log = logging.getLogger(__name__)

_RETRYABLE_STATUS = {408, 409, 425, 429, 500, 502, 503, 504}

#: Free models verified by hand against the *story run* schema on 2026-11-14 (ultra:
#: full 20-step run; super-vl: answers the schema, may return a short run the Validator
#: repairs). The live ``/models`` catalogue changes constantly, so these exist to make
#: discovery failure and primary selection safe -- not to be the model list.
VERIFIED_FREE_MODELS: tuple[str, ...] = (
    "nvidia/nemotron-3-ultra-550b-a55b:free",
    "nvidia/nemotron-3.5-super-vl:free",
)

#: Broader static floor, used only when the live catalogue is unreachable and by the
#: credit-exhaustion loop. Includes models that answer simpler schemas (and may fail the
#: story schema); they are attempts of last resort, not recommendations.
FREE_OPENROUTER_MODELS = [
    "nvidia/nemotron-3-ultra-550b-a55b:free",
    "nvidia/nemotron-3.5-super-vl:free",
    "nvidia/nemotron-3.5-lightning:free",
    "cohere/north-mini-code:free",
    "recursive/flint-v1.0:free",
    "dots-studio/dots-3-note-preview:free",
]

#: How long a discovered catalogue is trusted. Free model lists change slowly; an hour
#: avoids hammering ``/models`` on every runtime build while still picking up new ids.
FREE_MODEL_CACHE_TTL_S = 3600.0
_FREE_MODEL_CACHE: tuple[float, list[str]] | None = None


def reset_free_model_cache() -> None:
    """Clear the catalogue cache. Used by tests and by a redeploy that needs fresh ids."""
    global _FREE_MODEL_CACHE
    _FREE_MODEL_CACHE = None


def shuffled_models(models: list[str] | tuple[str, ...], rng: random.Random | None = None) -> list[str]:
    """A shuffled copy. Deterministic when an ``rng`` is supplied (tests)."""
    result = list(dict.fromkeys(models))
    (rng or random).shuffle(result)
    return result


def get_shuffled_free_models() -> list[str]:
    """Static verified ids, shuffled. The live catalogue is preferred by callers."""
    return shuffled_models(FREE_OPENROUTER_MODELS)


def _pricing_is_zero(value: Any) -> bool | None:
    try:
        return float(value) == 0.0
    except (TypeError, ValueError):
        return None


#: Families that are not chat/completion models even when they are free. OpenRouter
#: occasionally lists audio, music and image previews with zero pricing and no output
#: modality metadata; a fallback attempt on one is a wasted turn.
_NON_TEXT_HINTS: tuple[str, ...] = (
    "lyria", "whisper", "tts", "text-to-speech", "speech", "audio", "musicgen",
    "embedding", "embed", "image", "video", "flux", "stable-diffusion", "sdxl",
    "dall-e", "veo", "kling", "runway", "clip-preview",
)

#: Parameters that mean a model can enforce a JSON schema server-side. Their presence
#: is not guaranteed (some aggregators omit it), which is why it ranks rather than
#: filters.
_STRUCTURED_PARAMS = frozenset({"structured_outputs", "response_format"})


def _supports_structured_outputs(model: dict[str, Any]) -> bool:
    return bool(_STRUCTURED_PARAMS & set(model.get("supported_parameters") or []))


def _is_free_text_model(model: dict[str, Any]) -> bool:
    """Whether a ``/models`` entry is a free text model.

    OpenRouter exposes zero pricing as strings, and marks free variants with a
    ``:free`` suffix; either signal is accepted, but both prompt and completion must be
    zero when pricing is present. Image-output models are excluded -- the story engine
    needs JSON, not pictures.
    """
    model_id = str(model.get("id") or "")
    if not model_id:
        return False
    lowered = model_id.lower()
    if any(hint in lowered for hint in _NON_TEXT_HINTS):
        return False
    architecture = model.get("architecture") or {}
    outputs = architecture.get("output_modalities")
    if isinstance(outputs, list) and outputs and "text" not in outputs:
        return False
    modality = str(architecture.get("modality") or "")
    if modality and "->text" not in modality:
        return False

    pricing = model.get("pricing") or {}
    prompt = _pricing_is_zero(pricing.get("prompt"))
    completion = _pricing_is_zero(pricing.get("completion"))
    if prompt is not None and completion is not None:
        return prompt and completion
    return model_id.endswith(":free")


async def discover_free_models(
    *,
    api_key: str = "",
    base_url: str = "https://openrouter.ai/api/v1",
    timeout: float = 5.0,
    ttl: float = FREE_MODEL_CACHE_TTL_S,
) -> list[str]:
    """Fetch, filter and shuffle the current free text models from OpenRouter.

    Fail-open: an unreachable or malformed catalogue returns the last good cache, or an
    empty list so the caller can fall back to ``VERIFIED_FREE_MODELS``. The models
    endpoint is public, so this works before any generation call and costs no tokens.
    """
    global _FREE_MODEL_CACHE
    now = time.monotonic()
    if _FREE_MODEL_CACHE and now - _FREE_MODEL_CACHE[0] < ttl:
        return list(_FREE_MODEL_CACHE[1])

    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(f"{base_url.rstrip('/')}/models", headers=headers)
            response.raise_for_status()
            data = response.json()
        entries = data.get("data") if isinstance(data, dict) else data
        if not isinstance(entries, list):
            raise ValueError("models response had no data list")
        candidates = [
            entry for entry in entries
            if isinstance(entry, dict) and _is_free_text_model(entry)
        ]
        if not candidates:
            raise ValueError("no free text models in the catalogue")
    except Exception:  # noqa: BLE001 - discovery must never block a runtime build
        log.warning("OpenRouter free-model discovery failed; using cached or verified ids",
                    exc_info=True)
        return list(_FREE_MODEL_CACHE[1]) if _FREE_MODEL_CACHE else []

    # Shuffle within each group, but try models that can enforce the schema server-side
    # first: they remove a whole class of malformed-output failures. Hand-verified ids
    # come before other schema-capable models, so a live catalogue full of new names
    # cannot displace the fallback that is known to answer this game's schema. Within
    # every group the order is random, drawn from the live list.
    strict = [str(entry["id"]) for entry in candidates if _supports_structured_outputs(entry)]
    relaxed = [str(entry["id"]) for entry in candidates if not _supports_structured_outputs(entry)]
    verified = [model for model in strict if model in VERIFIED_FREE_MODELS]
    other_strict = [model for model in strict if model not in VERIFIED_FREE_MODELS]
    ordered = (
        shuffled_models(verified)
        + shuffled_models(other_strict)
        + shuffled_models(relaxed)
    )
    _FREE_MODEL_CACHE = (now, ordered)
    log.info(
        "discovered %d free OpenRouter text models (%d schema-capable, %d verified)",
        len(ordered), len(strict), len(verified),
    )
    return list(ordered)


def pick_primary_model(discovered: list[str]) -> str:
    """Choose a primary from a shuffled catalogue, preferring a hand-verified id.

    A random id is a bad first impression if it cannot answer the schema; a verified one
    that exists in the live catalogue is the stable choice. If none is present, take the
    first shuffled entry.
    """
    for model in VERIFIED_FREE_MODELS:
        if model in discovered:
            return model
    return discovered[0] if discovered else VERIFIED_FREE_MODELS[0]


def requires_parameter_relaxation(exc: Any) -> bool:
    """True when no route supports ``response_format`` on this model.

    Free OpenRouter models frequently have no provider endpoint that accepts the
    structured-output parameter, so the router answers 404 with "No endpoints found that
    can handle the requested parameters". Retrying without the routing requirement lets
    the model answer and puts the schema enforcement back where it belongs: local
    validation plus the one JSON-repair round-trip. Paid models keep the strict route.
    """
    text = str(exc).lower()
    return "no endpoints found" in text and "parameter" in text


def is_credit_exhausted_error(exc_or_status: Any, message: str = "") -> bool:
    code = None
    if isinstance(exc_or_status, int):
        code = exc_or_status
    else:
        for attr in ("status_code", "http_status", "code"):
            val = getattr(exc_or_status, attr, None)
            if isinstance(val, int):
                code = val
                break
        if code is None and hasattr(exc_or_status, "response"):
            resp = getattr(exc_or_status, "response", None)
            code = getattr(resp, "status_code", None)

    msg_str = f"{exc_or_status} {message}".lower()
    if code == 402:
        return True

    if "rate limit" in msg_str and not any(k in msg_str for k in ("credit", "payment", "balance")):
        return False

    credit_keywords = (
        "402",
        "credit",
        "payment required",
        "run out of credits",
        "insufficient balance",
        "insufficient credits",
        "insufficient_quota",
        "exceeded your current quota",
        "out of credit",
    )
    return any(kw in msg_str for kw in credit_keywords)


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

    @property
    def model(self) -> str:
        """The model id, recorded in traces so a regression can be attributed."""
        return self._model

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
        reset_usage()
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

        try:
            raw = await self._complete_text(payload)
        except Exception as exc:
            if payload.get("provider") and requires_parameter_relaxation(exc):
                log.info(
                    "no strict-schema route for %s; retrying without provider routing "
                    "and validating locally", self._model,
                )
                relaxed = {key: value for key, value in payload.items() if key != "provider"}
                raw = await self._complete_text(relaxed)
            elif is_credit_exhausted_error(exc):
                log.warning("OpenRouter credits exhausted (%s), falling back to shuffled free models", exc)
                catalogue = await discover_free_models(
                    api_key=self._api_key,
                    base_url=self._base_url,
                    timeout=min(5.0, self._timeout),
                )
                candidates = [
                    model for model in (catalogue or FREE_OPENROUTER_MODELS)
                    if model != self._model
                ]
                for free_model in shuffled_models(candidates):
                    try:
                        log.info("Retrying complete_json with free fallback model: %s", free_model)
                        fb_payload = dict(payload)
                        fb_payload["model"] = free_model
                        raw = await self._complete_text(fb_payload)
                        return self._parse(raw)
                    except Exception as fb_exc:
                        log.warning("Free model %s failed: %s", free_model, fb_exc)
                        continue
                raise
            else:
                raise
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
        record_usage(data.get("usage") if isinstance(data, dict) else None)
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

    async def generate(
        self,
        prompt: str,
        *,
        width: int = 1024,
        height: int = 576,
        seed: int | None = None,
        negative: str | None = None,
    ) -> tuple[bytes, str]:
        payload: dict[str, Any] = {"model": self._model, "prompt": prompt}
        if seed is not None:
            # Sent as a hint. Routes that support it hold the subject steady across
            # requests; routes that do not drop the unknown field rather than erroring,
            # which is why it is not gated on the model.
            payload["seed"] = seed
        # `negative` is deliberately not folded into the prompt: this endpoint has no
        # negative field, and naming what you do not want in the prompt itself is how you
        # get it drawn.
        data = await self._post("/images", payload, ImageError)
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
