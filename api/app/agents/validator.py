"""Validation Agent — PRD §9.6, enforcing the five hard rules of PRD §24.

Philosophy: **repair, then truncate.** A run is never discarded for something fixable.
Out-of-range deltas are clamped, unknown characters are dropped, a teleport is snapped
back to the current location. Only when a step cannot be salvaged -- the model spoke for
the player, or wrote something that fails the content screen -- is the run cut at that
point and everything after it discarded.

The engine then guarantees the invariant the playback loop depends on: **every run ends
in exactly one blocking step.**
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.agents.safety import SafetyFilter
from app.content.world import World
from app.domain.enums import StepType
from app.domain.state import GameSession
from app.domain.story import Choice, GeneratedRun, GeneratedStep, VisualSpec
from app.domain.validation import ValidationReport, Violation

#: Deliberate second-person acts. Involuntary perception ("you feel the wind", "you can
#: see the town") is deliberately absent -- describing what reaches the player is the
#: narrator's job; deciding what they do with it is not.
_AGENCY_VERBS = (
    "decide|agree|disagree|refuse|accept|promise|confess|admit|apologi[sz]e|answer|reply|respond"
    r"|say|tell|ask|shout|yell|whisper|call out|nod|shake your head|agree to"
    r"|kiss|hug|embrace|grab|reach out|take (?:her|his|their) hand|hold (?:her|his|their) hand"
    r"|kneel|follow|leave|walk away|walk over|step (?:forward|back)|lean in|turn away"
    r"|choose|pick|decline|insist|explain|confide|invite"
)
_AGENCY = re.compile(
    r"\byou(?:'ve|'d|'ll|r self| have| had| will| then| just)?\s+"
    r"(?:just |then |slowly |finally |quietly |immediately |carefully )*"
    rf"(?:{_AGENCY_VERBS})\b",
    re.IGNORECASE,
)
_SENTENCE = re.compile(r"(?<=[.!?])\s+")
_FLAG_KEY = re.compile(r"^[a-z][a-z0-9_]{0,39}$")

#: Flags the engine owns. ``_commit_step`` merges ``flags_set`` straight into world state,
#: so without this a narration step could forge the marker that says the story is over.
_RESERVED_FLAGS = frozenset({"ending", "ending_partner", "ended"})

#: Per-step flag budget. World flags are never pruned and every one of them is rendered
#: into the prompt, so an enthusiastic model would add ~1,100 tokens to every future call.
MAX_FLAGS_PER_STEP = 3

_PLAYER_SPEAKERS = {"player", "you", "protagonist", "mc", "me"}
_NARRATOR_SPEAKERS = {"narrator", "narration", ""}

#: Fillers used only to bring a short option list up to MIN_CHOICES. They are worded to
#: be true of any scene: the validator sees no ``Directive``, so it cannot know whether
#: the beat went well. A filler that leaned warm after a rebuff ("Tell her you missed
#: her") would actively misrepresent the scene, which is worse than being plain.
_TOP_UPS_WITH_TARGET: tuple[str, ...] = (
    "Say nothing, and let {target} fill the silence.",
    "Change the subject.",
    "Ask {target} what they meant by that.",
    "Give {target} a moment.",
    "Say what you were actually thinking.",
)
_TOP_UPS_ALONE: tuple[str, ...] = (
    "Say nothing.",
    "Let the moment pass.",
    "Take it in for a second longer.",
    "Go and find someone.",
    "Say what you were actually thinking.",
)


def strip_agency(text: str) -> tuple[str, bool]:
    """Remove sentences that narrate a player decision. Returns ``(kept, removed_any)``."""
    sentences = [s for s in _SENTENCE.split(text.strip()) if s.strip()]
    kept = [s for s in sentences if not _AGENCY.search(s)]
    return " ".join(kept).strip(), len(kept) != len(sentences)


@dataclass
class Validator:
    world: World
    safety: SafetyFilter
    max_delta: int = 5
    max_steps: int = 5
    min_choices: int = 3
    max_choices: int = 5

    def validate(
        self,
        run: GeneratedRun,
        session: GameSession,
        *,
        allow_ending: bool = False,
        is_opening: bool = False,
    ) -> ValidationReport:
        """Repair a generated run into something the engine can commit.

        ``allow_ending`` is the engine's permission slip for the final run of the story.
        It is the only way a step can become ``StepType.ending``: the wire schema cannot
        express one, so the model cannot ask for it, and the scripted finale only gets to
        keep its ending step when the Director has said so.
        """
        violations: list[Violation] = []
        kept: list[GeneratedStep] = []
        location = session.world.location
        known = set(self.world.character_ids)
        step_limit = len(run.steps) if is_opening else self.max_steps

        def flag(rule: str, detail: str, remedy: str, index: int | None) -> None:
            violations.append(
                Violation(rule=rule, detail=detail, remedy=remedy, step_index=index)  # type: ignore[arg-type]
            )

        for index, original in enumerate(run.steps):
            if len(kept) >= step_limit:
                flag("run_structure", f"run exceeded {step_limit} steps", "truncated", index)
                break

            step = original.model_copy(deep=True)

            if step.type is StepType.ending and not allow_ending:
                flag(
                    "run_structure",
                    "ending proposed before the story had earned one",
                    "rewritten",
                    index,
                )
                step.type = StepType.narration
                step.next_choices = []

            # -- content safety (PRD §28) ------------------------------------------------
            verdict = self.safety.check(step.text_body())
            if not verdict.allowed:
                flag("content_safety", f"generated text matched {verdict.reason}", "rejected", index)
                break

            # -- Rule 3: world consistency ----------------------------------------------
            if self.world.location(step.location) is None:
                flag("world_consistency", f"unknown location {step.location!r}", "rewritten", index)
                step.location = location
            elif step.location != location:
                if step.type is StepType.transition:
                    location = step.location
                else:
                    flag(
                        "world_consistency",
                        f"moved to {step.location!r} without a transition step",
                        "rewritten",
                        index,
                    )
                    step.location = location

            # -- Rule 2: character consistency ------------------------------------------
            resolved_cast: list[str] = []
            for name in step.characters:
                resolved = self.world.resolve_character(name)
                if resolved:
                    resolved_cast.append(resolved)
                else:
                    flag("character_consistency", f"unknown character {name!r}", "rewritten", index)
            step.characters = list(dict.fromkeys(resolved_cast))

            # -- Rule 1: player agency ---------------------------------------------------
            if step.dialogue:
                speaker = step.dialogue.speaker.strip().lower()
                if speaker in _PLAYER_SPEAKERS:
                    flag(
                        "player_agency",
                        "generated dialogue spoken by the player",
                        "truncated",
                        index,
                    )
                    break
                resolved_speaker = self.world.resolve_character(speaker)
                if resolved_speaker is None and speaker not in _NARRATOR_SPEAKERS:
                    flag(
                        "character_consistency",
                        f"dialogue from unknown speaker {step.dialogue.speaker!r}",
                        "dropped",
                        index,
                    )
                    continue
                if resolved_speaker:
                    step.dialogue.speaker = resolved_speaker
                    if resolved_speaker not in step.characters:
                        step.characters.append(resolved_speaker)
                else:
                    step.narration = " ".join(filter(None, [step.narration, step.dialogue.text]))
                    step.dialogue = None

            if step.narration and not allow_ending:
                # Rule 1 protects a decision the player has not made yet. The FINAL RUN has
                # no next decision at any point in it, so the rule protects nothing here --
                # and leaving it on gutted the ending, because _AGENCY_VERBS covers exactly
                # the verbs an ending is made of (promise, say, leave, follow).
                #
                # Scoping this to `type is ending` did not work: the model cannot emit that
                # type, so a model-written ending arrives as narration and is only promoted
                # after this loop has already stripped it.
                cleaned, removed = strip_agency(step.narration)
                if removed:
                    flag("player_agency", "narration acted for the player", "rewritten", index)
                step.narration = cleaned or None

            # -- Rule 4: state consistency ----------------------------------------------
            changes = {}
            for name, delta in step.relationship_changes.items():
                target = self.world.resolve_character(name)
                if target is None:
                    flag("state_consistency", f"delta for unknown character {name!r}", "dropped", index)
                    continue
                clamped, offenders = delta.clamped(self.max_delta)
                if offenders:
                    flag(
                        "state_consistency",
                        f"{target} delta out of range ({', '.join(offenders)})",
                        "clamped",
                        index,
                    )
                if not clamped.is_zero():
                    changes[target] = clamped
            step.relationship_changes = changes

            emotions = {}
            for name, mood in step.emotion.items():
                target = self.world.resolve_character(name)
                if target:
                    emotions[target] = mood
            step.emotion = emotions

            flags = {}
            for key, value in step.flags_set.items():
                normalised = str(key).strip().lower().replace(" ", "_")
                if normalised in _RESERVED_FLAGS:
                    flag("state_consistency", f"reserved flag {normalised!r}", "dropped", index)
                elif not _FLAG_KEY.match(normalised):
                    flag("state_consistency", f"illegal flag key {key!r}", "dropped", index)
                elif len(flags) >= MAX_FLAGS_PER_STEP:
                    flag(
                        "state_consistency",
                        f"more than {MAX_FLAGS_PER_STEP} flags on one step",
                        "dropped",
                        index,
                    )
                else:
                    flags[normalised] = value
            step.flags_set = flags

            if step.memory:
                target = self.world.resolve_character(step.memory.character)
                if target is None:
                    flag("state_consistency", "memory for unknown character", "dropped", index)
                    step.memory = None
                else:
                    step.memory.character = target

            # -- run structure -----------------------------------------------------------
            if step.next_choices and step.type is StepType.ending:
                step.next_choices = []
            elif step.next_choices and not step.type.is_blocking:
                flag("run_structure", f"{step.type.value} step carried choices", "rewritten", index)
                step.type = StepType.choice

            if step.type is StepType.choice:
                offered = self._normalise_choices(step.next_choices)
                if len(offered) > self.max_choices:
                    flag(
                        "run_structure",
                        f"{len(offered)} options offered, capped at {self.max_choices}",
                        "truncated",
                        index,
                    )
                    offered = offered[: self.max_choices]
                if len(offered) < self.min_choices:
                    # Topped up rather than downgraded to free text: a short list is the
                    # model under-delivering, and answering that by taking the menu away
                    # from the player is a strange punishment.
                    shortfall = self.min_choices - len(offered)
                    offered = self._top_up(step, offered)
                    flag(
                        "run_structure",
                        f"only {self.min_choices - shortfall} option(s) offered, topped up to {len(offered)}",
                        "rewritten",
                        index,
                    )
                step.next_choices = self._renumber(offered)
            else:
                step.next_choices = []

            if not (step.narration or step.dialogue or step.is_blocking or step.flags_set):
                flag("continuity", "step had no content", "dropped", index)
                continue

            kept.append(step)

            if step.is_terminal and not is_opening:
                if index < len(run.steps) - 1:
                    flag(
                        "run_structure",
                        f"discarded {len(run.steps) - index - 1} step(s) after the decision point",
                        "truncated",
                        index,
                    )
                break

        if allow_ending and kept:
            kept = self._promote_ending(kept, flag)
        elif kept and not kept[-1].is_terminal:
            flag("run_structure", "run did not end at a player decision", "rewritten", None)
            kept.append(self._terminator(kept[-1]))

        return ValidationReport(steps=kept, violations=violations)

    def _promote_ending(self, kept: list[GeneratedStep], flag) -> list[GeneratedStep]:
        """Turn the last run of the story into an actual ending.

        The engine does this rather than the model. A finale run comes back looking like
        any other run -- often with a decision point stapled on out of habit -- so the
        trailing question is dropped and whatever prose is left becomes the ending step.
        """
        if kept[-1].type is StepType.ending:
            return kept

        while kept and kept[-1].is_blocking:
            flag("run_structure", "dropped a decision point from the final run", "truncated", None)
            kept.pop()

        if not kept:
            return kept

        kept[-1].type = StepType.ending
        kept[-1].next_choices = []
        return kept

    # -- helpers -------------------------------------------------------------------------

    @staticmethod
    def _dedupe_key(text: str) -> str:
        """Punctuation-insensitive, so "I promised." and "I promised!" are one option."""
        return "".join(ch for ch in text.lower() if ch.isalnum() or ch.isspace()).strip()

    def _normalise_choices(self, choices: list[Choice]) -> list[Choice]:
        seen: set[str] = set()
        out: list[Choice] = []
        for choice in choices:
            text = " ".join(choice.text.split())
            key = self._dedupe_key(text)
            if not text or not key or key in seen:
                continue
            seen.add(key)
            out.append(Choice(id="pending", text=text))
        return out

    def _top_up(self, step: GeneratedStep, offered: list[Choice]) -> list[Choice]:
        """Bring a short list up to ``min_choices`` from an authored, scene-neutral bank.

        Deterministic: the same step always tops up the same way, which matters because
        speculative prefetch keys branches by choice id.
        """
        speaker = step.dialogue.speaker if step.dialogue else None
        target_id = self.world.resolve_character(speaker) or next(
            (c for c in step.characters if self.world.character(c)), None
        )
        character = self.world.character(target_id) if target_id else None

        if character:
            bank = tuple(line.format(target=character.name.split()[0]) for line in _TOP_UPS_WITH_TARGET)
        else:
            bank = _TOP_UPS_ALONE

        taken = {self._dedupe_key(choice.text) for choice in offered}
        out = list(offered)
        for line in bank:
            if len(out) >= self.min_choices:
                break
            if self._dedupe_key(line) in taken:
                continue
            taken.add(self._dedupe_key(line))
            out.append(Choice(id="pending", text=line))
        return out

    @staticmethod
    def _renumber(choices: list[Choice]) -> list[Choice]:
        return [Choice(id=f"choice_{i + 1}", text=c.text) for i, c in enumerate(choices)]

    @staticmethod
    def _terminator(previous: GeneratedStep) -> GeneratedStep:
        """A free-text prompt, so the player always gets control back."""
        return GeneratedStep(
            type=StepType.prompt,
            location=previous.location,
            characters=list(previous.characters),
            narration=None,
            visual=previous.visual or VisualSpec(background=previous.location),
        )
