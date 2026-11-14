"""Choice quality — the intelligence PRD's FR-06.

The engine already guarantees *three to five* options. This module asks a harder
question: are they actually different decisions? Two options that paraphrase each other
offer no agency, and a menu where every road is supportive is not a choice either.

The assessment is deterministic (token overlap plus a small intent lexicon), so it runs
offline and cannot itself be prompt-injected. ``repair`` only ever removes a near-
duplicate and tops the list back up from the caller's own bank; it does not invent new
directions and it never guarantees an outcome.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.domain.story import Choice

#: Ordered: the first category whose pattern matches wins, so specific beats generic.
_CATEGORIES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("emotional", (
        r"\b(?:love|adore|feel(?:ings)?|confess|sorry|apolog|forgive|miss you|need you)\b",
        r"\b(?:cry|hug|kiss|hold (?:her|his|their) hand|blush)\b",
    )),
    ("confrontational", (
        r"\b(?:confront|accuse|challenge|demand|refuse|call (?:her|him|them) out)\b",
        r"\b(?:angry|furious|argue|fight|push back|that'?s not fair|how dare)\b",
    )),
    ("investigative", (
        r"\b(?:ask|question|find out|investigate|press|why|what happened|who)\b",
        r"\b(?:tell me|explain|clarify|look (?:for|into)|check)\b",
    )),
    ("supportive", (
        r"\b(?:help|support|comfort|reassure|listen|be there|protect|defend)\b",
        r"\b(?:stay (?:with|by)|i'?m here|you can count on me|take your time|it'?s okay)\b",
    )),
    ("strategic", (
        r"\b(?:lie|deceive|negotiate|bargain|distract|threaten|promise|trade|bribe)\b",
        r"\b(?:change the subject|deflect|pretend|keep it secret|use)\b",
    )),
    ("neutral", (
        r"\b(?:say nothing|wait|observe|watch|leave|walk away|nod|shrug)\b",
        r"\b(?:do nothing|stay silent|let the moment|give (?:her|him|them) (?:a )?(?:moment|space))\b",
    )),
)

_COMPILED = tuple(
    (name, tuple(re.compile(pattern, re.IGNORECASE) for pattern in patterns))
    for name, patterns in _CATEGORIES
)

#: Above this pairwise similarity two options are paraphrases, not alternatives.
DUPLICATE_SIMILARITY = 0.7
#: Below this the menu is considered too samey to offer meaningful agency.
MIN_GOOD_SCORE = 0.55


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9']+", text.lower()) if len(t) > 2}


def jaccard(left: str, right: str) -> float:
    a, b = _tokens(left), _tokens(right)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def classify(text: str) -> str:
    for name, patterns in _COMPILED:
        if any(pattern.search(text) for pattern in patterns):
            return name
    return "neutral"


#: Phrasings that are the same decision wearing different words. Deterministic and
#: deliberately small: it exists to stop a menu offering "Say nothing" / "Stay silent"
#: / "Do nothing" as three choices, not to be a general paraphrase detector.
_INTENTIONS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("silence", (r"\bsay nothing\b", r"\bstay silent\b", r"\bdo nothing\b",
                 r"\bkeep quiet\b", r"\bstay quiet\b", r"\blet the moment\b")),
    ("leave", (r"\bwalk away\b", r"\bleave\b", r"\bgo home\b")),
    ("ask", (r"\bask\b", r"\bquestion\b", r"\bfind out\b", r"\bpress\b")),
    ("help", (r"\boffer to help\b", r"\bhelp\b", r"\bassist\b")),
    ("apologise", (r"\bapolog", r"\bsorry\b", r"\bmy fault\b")),
)

_COMPILED_INTENTIONS = tuple(
    (name, tuple(re.compile(pattern, re.IGNORECASE) for pattern in patterns))
    for name, patterns in _INTENTIONS
)


def intention(text: str) -> str | None:
    """A coarse identity for a choice, used to catch paraphrases."""
    for name, patterns in _COMPILED_INTENTIONS:
        if any(pattern.search(text) for pattern in patterns):
            return name
    return None


@dataclass
class ChoiceAssessment:
    score: float = 1.0
    similarity: float = 0.0
    intent_diversity: float = 1.0
    relevance: float = 1.0
    categories: list[str] = field(default_factory=list)
    duplicate_pairs: list[tuple[int, int]] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)


def assess(choices: list[Choice], *, context_text: str = "", min_choices: int = 3) -> ChoiceAssessment:
    """Score one menu. Deterministic and cheap; safe to run on every generated run."""
    if not choices:
        return ChoiceAssessment(score=0.0, issues=["no options were offered"])

    categories = [classify(choice.text) for choice in choices]
    pairs: list[tuple[int, int]] = []
    highest = 0.0
    for i, left in enumerate(choices):
        for j in range(i + 1, len(choices)):
            right = choices[j]
            similarity = jaccard(left.text, right.text)
            highest = max(highest, similarity)
            same_intention = (
                intention(left.text) is not None
                and intention(left.text) == intention(right.text)
            )
            if similarity >= DUPLICATE_SIMILARITY or same_intention:
                pairs.append((i, j))

    distinct = len(set(categories))
    intent_diversity = min(1.0, distinct / max(1, min(min_choices, len(choices))))
    context_tokens = _tokens(context_text)
    if context_tokens:
        relevance = sum(
            1 for choice in choices if _tokens(choice.text) & context_tokens
        ) / len(choices)
    else:
        relevance = 1.0

    score = max(0.0, min(1.0,
        0.45 * (1.0 - highest)
        + 0.35 * intent_diversity
        + 0.20 * relevance
    ))

    issues: list[str] = []
    if pairs:
        issues.append("some options paraphrase each other")
    if distinct < min(2, len(choices)):
        issues.append("every option expresses the same intention")
    if relevance < 0.25:
        issues.append("options are disconnected from the scene")

    return ChoiceAssessment(
        score=round(score, 3),
        similarity=round(highest, 3),
        intent_diversity=round(intent_diversity, 3),
        relevance=round(relevance, 3),
        categories=categories,
        duplicate_pairs=pairs,
        issues=issues,
    )


def repair(
    choices: list[Choice],
    *,
    bank: tuple[str, ...],
    min_choices: int,
    context_text: str = "",
) -> list[Choice]:
    """Drop near-duplicates and top up from a scene-neutral bank.

    Returns the original list when there was nothing to repair, so the caller can tell
    whether anything changed.
    """
    if not choices:
        return choices
    kept: list[Choice] = []
    for choice in choices:
        duplicate = any(
            jaccard(choice.text, other.text) >= DUPLICATE_SIMILARITY
            or (
                intention(choice.text) is not None
                and intention(choice.text) == intention(other.text)
            )
            for other in kept
        )
        if duplicate:
            continue
        kept.append(choice)

    taken = {choice.text.strip().lower() for choice in kept}
    for line in bank:
        if len(kept) >= min_choices:
            break
        if line.strip().lower() in taken:
            continue
        kept.append(Choice(id="pending", text=line))
        taken.add(line.strip().lower())

    if len(kept) == len(choices) and all(
        choice.id == original.id for choice, original in zip(kept, choices)
    ):
        return choices
    return [Choice(id=f"choice_{i + 1}", text=choice.text) for i, choice in enumerate(kept)]
