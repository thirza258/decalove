"""Evidence-based player behaviour modelling — the intelligence PRD's FR-07.

The engine already knows what the player did; this turns a delivered batch into at most
one observation per dimension. Observations are keyed by batch id, so a retried delivery
is idempotent, and each one moves a dimension by a fraction of its range. Confidence is
derived from how many observations exist, which is what stops the first dramatic turn
from defining the player for the rest of the save.

Deliberately not a model call: a profile that drifts with the writer's mood is worse
than one that is plainly derived from actions.
"""

from __future__ import annotations

from app.domain.behavior import PlayerBehaviorProfile
from app.domain.intent import PlayerIntent
from app.domain.story import GeneratedStep

#: Each action's reading on each dimension. ``None`` means "this action says nothing
#: about this dimension", which is different from "it says the player is average".
_ACTION_SIGNALS: dict[str, dict[str, float]] = {
    "help": {"empathy": 1.0, "sociability": 0.8, "conflict_response": 0.4},
    "compliment": {"empathy": 0.7, "sociability": 0.9},
    "apologise": {"empathy": 0.9, "emotional_expression": 0.9, "conflict_response": 0.3},
    "tease": {"conflict_response": 1.0, "sociability": 0.7, "empathy": 0.2},
    "confess": {"emotional_expression": 1.0, "risk_tolerance": 0.9},
    "ask_about": {"curiosity": 1.0, "sociability": 0.7},
    "invite_character": {"sociability": 1.0, "risk_tolerance": 0.6},
    "talk_to": {"sociability": 0.9},
    "observe": {"sociability": 0.2, "conflict_response": 0.2, "risk_tolerance": 0.2},
    "move_location": {"curiosity": 0.6},
}

_EMOTION_SIGNAL = {"emotional_expression": 1.0}
_RISK_SIGNALS = {"high": 1.0, "medium": 0.5, "low": 0.2}


def observe_delivery(
    profile: PlayerBehaviorProfile,
    intent: PlayerIntent | None,
    delivered: list[GeneratedStep],
    *,
    batch_id: str,
    step_index: int = 0,
) -> None:
    """Fold one delivered run into the profile. Idempotent by batch id."""
    if not intent or not batch_id:
        return
    signals: dict[str, float] = dict(_ACTION_SIGNALS.get(intent.action, {}))
    if intent.emotion:
        signals.update(_EMOTION_SIGNAL)
    signals["risk_tolerance"] = _RISK_SIGNALS.get(intent.risk.value, 0.5)

    for dimension, target in signals.items():
        profile.observe(dimension, target, step_id=batch_id)

    # Commitment is read from the story, not from a verb: a promise the delivered run
    # marked broken is evidence, a fulfilled one is counter-evidence.
    for step in delivered:
        memory = step.memory
        if memory is None or memory.event_type not in ("promise", "commitment", "oath"):
            continue
        target = {"fulfilled": 1.0, "broken": 0.0}.get(memory.status)
        if target is not None:
            profile.observe("commitment", target, step_id=batch_id)
            break

    profile.updated_at_step = max(profile.updated_at_step, step_index)
