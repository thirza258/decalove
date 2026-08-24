"""The LLM wire contract — strict JSON Schema and the DTO -> domain conversion."""

from __future__ import annotations

import pytest

from app.domain.intent import PlayerIntent
from app.llm.dto import LLMRun
from app.llm.openrouter import OpenRouterChat
from app.llm.schema import strict_schema


def walk(node, path="#"):
    """Yield every object schema, so strict-mode rules can be asserted everywhere."""
    if isinstance(node, dict):
        if node.get("type") == "object" or "properties" in node:
            yield path, node
        for key, value in node.items():
            yield from walk(value, f"{path}/{key}")
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from walk(value, f"{path}[{index}]")


@pytest.mark.parametrize("model", [LLMRun, PlayerIntent])
def test_strict_schema_satisfies_openrouter_rules(model):
    schema = strict_schema(model)
    seen = 0
    for path, node in walk(schema):
        seen += 1
        assert node.get("additionalProperties") is False, path
        assert set(node.get("required", [])) == set(node.get("properties", {})), path
    assert seen >= 1


def test_strict_schema_strips_unsupported_keywords():
    schema = strict_schema(LLMRun)
    for path, node in walk(schema):
        assert "default" not in node, path


def test_strict_schema_keeps_fields_named_like_keywords():
    """A field called ``title`` must survive; only the *keyword* ``title`` is stripped."""
    from pydantic import BaseModel

    class Book(BaseModel):
        title: str
        default: int = 0

    schema = strict_schema(Book)
    assert set(schema["properties"]) == {"title", "default"}


def test_llm_run_converts_entry_lists_into_domain_maps():
    payload = {
        "summary": "Aiko was surprised.",
        "steps": [
            {
                "type": "dialogue",
                "location": "rooftop",
                "characters": ["aiko"],
                "narration": None,
                "dialogue": {"speaker": "aiko", "text": "You really came...", "emotion": "surprised"},
                "emotions": [{"character": "aiko", "emotion": "surprised"}],
                "relationship_changes": [{"character": "aiko", "affection": 3, "trust": 1}],
                "flags_set": [{"key": "met_on_roof", "value": "true"}],
                "memory": None,
                "next_choices": [],
                "visual": {"background": "rooftop", "character": "aiko", "expression": "surprised"},
            }
        ],
    }
    run = LLMRun.model_validate(payload).to_domain()
    step = run.steps[0]
    assert step.emotion == {"aiko": "surprised"}
    assert step.relationship_changes["aiko"].affection == 3
    assert step.flags_set == {"met_on_roof": "true"}
    assert step.visual.background == "rooftop"


@pytest.mark.parametrize(
    "raw",
    ['{"a": 1}', '```json\n{"a": 1}\n```', '```\n{"a": 1}\n```'],
)
def test_parser_tolerates_markdown_fences(raw):
    assert OpenRouterChat._parse(raw) == {"a": 1}


def test_parser_rejects_non_objects():
    from app.llm.base import LLMError

    with pytest.raises(LLMError):
        OpenRouterChat._parse("[1, 2, 3]")
