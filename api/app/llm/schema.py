"""Pydantic -> strict JSON Schema for structured outputs.

OpenRouter forwards ``response_format: {"type": "json_schema", "json_schema": {...,
"strict": true}}`` to providers that support it. Strict mode has rules Pydantic's default
output does not satisfy:

* every object needs ``additionalProperties: false``
* every property must be listed in ``required`` (optionality is expressed as a nullable
  ``anyOf``, not by omission)
* ``default`` is not a supported keyword

``strict_schema()`` rewrites a model's schema to satisfy all three.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

#: Keywords strict mode rejects or ignores. Only stripped where they are *keywords* --
#: never where they happen to be the name of a field (inside ``properties``/``$defs``).
_STRIPPED_KEYWORDS = ("default", "title", "examples")

#: Maps whose keys are user-defined names rather than JSON-Schema keywords.
_NAME_MAPS = ("properties", "$defs", "definitions", "patternProperties")


def _walk(node: Any, *, is_name_map: bool = False) -> Any:
    if isinstance(node, list):
        return [_walk(item) for item in node]
    if not isinstance(node, dict):
        return node

    if is_name_map:
        return {key: _walk(value) for key, value in node.items()}

    out: dict[str, Any] = {}
    for key, value in node.items():
        if key in _STRIPPED_KEYWORDS:
            continue
        out[key] = _walk(value, is_name_map=key in _NAME_MAPS)

    if out.get("type") == "object" or "properties" in out:
        properties = out.get("properties") or {}
        out["properties"] = properties
        out["additionalProperties"] = False
        # Strict mode: everything is required; nullability carries the optionality.
        out["required"] = list(properties.keys())
    return out


def strict_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Return a strict-mode-safe JSON Schema for ``model``."""
    return _walk(model.model_json_schema())


def response_format(name: str, model: type[BaseModel], *, strict: bool = True) -> dict[str, Any]:
    """Build the ``response_format`` block for a chat completion request."""
    return {
        "type": "json_schema",
        "json_schema": {
            "name": name,
            "strict": strict,
            "schema": strict_schema(model),
        },
    }
