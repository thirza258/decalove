"""Content safety — PRD §28.

A coarse, fast, deterministic first line: it runs on player input before generation and
on model output before delivery, so a single bad turn cannot reach the screen. It is
**not** a substitute for a moderation model; ``SafetyFilter`` is small on purpose so a
hosted classifier can be layered in front of it later without changing callers.

The design bias is to *contain* rather than to punish: blocked player input is turned
into a harmless in-world non-action, not an error the player has to argue with.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

#: Patterns that must never appear in generated prose or reach the model as instructions.
_RULES: tuple[tuple[str, str], ...] = (
    (
        "sexual_content",
        r"\b(explicit sex|sex scene|nude|naked|undress|strip(?:ping)? (?:her|him|them)|genital|aroused|orgasm|penetrat)",
    ),
    ("self_harm", r"\b(kill (?:myself|yourself|herself|himself|themselves)|suicide|self[- ]harm|cut (?:my|your)self)\b"),
    ("graphic_violence", r"\b(gut(?:s|ted)? (?:him|her|them)|dismember|torture|mutilat|bleeding out|stab(?:s|bed)? (?:him|her|them) repeatedly)\b"),
    ("hate", r"\b(subhuman|ethnic cleansing|racial slur)\b"),
    ("dangerous_instructions", r"\b(how to (?:make|build) a (?:bomb|weapon)|synthesi[sz]e (?:meth|explosives)|pipe bomb)\b"),
    ("minor_sexualisation", r"\b(loli|shota|underage (?:sex|nude))\b"),
)

#: Attempts to talk to the model rather than to the character. Not dangerous, just not a
#: story action -- they are absorbed in-world instead of being executed.
_INJECTION = re.compile(
    r"(ignore (?:all |any )?(?:previous|prior|above) instructions"
    r"|you are (?:now )?(?:an? )?(?:ai|assistant|language model)"
    r"|system prompt"
    r"|disregard (?:your|the) (?:rules|instructions)"
    r"|jailbreak)",
    re.IGNORECASE,
)

_COMPILED = tuple((label, re.compile(pattern, re.IGNORECASE)) for label, pattern in _RULES)


@dataclass(frozen=True)
class SafetyVerdict:
    allowed: bool
    categories: tuple[str, ...] = ()
    injection: bool = False

    @property
    def reason(self) -> str:
        bits = list(self.categories)
        if self.injection:
            bits.append("prompt_injection")
        return ", ".join(bits) or "clean"


class SafetyFilter:
    def __init__(self, rating: str = "teen") -> None:
        self.rating = rating

    def check(self, text: str) -> SafetyVerdict:
        if not text:
            return SafetyVerdict(allowed=True)
        hits = tuple(label for label, pattern in _COMPILED if pattern.search(text))
        injection = bool(_INJECTION.search(text))
        return SafetyVerdict(allowed=not hits, categories=hits, injection=injection)

    def screen_input(self, text: str) -> tuple[bool, SafetyVerdict]:
        """``(usable, verdict)`` for player input. Injection is usable but not meaningful."""
        verdict = self.check(text)
        return verdict.allowed and not verdict.injection, verdict
