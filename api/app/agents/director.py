"""Director Agent — PRD §9.1 / §8 Method B.

Turns free-text player input into a bounded ``PlayerIntent``. Two implementations behind
one call: the LLM when a key is configured, and a keyword parser when it is not. The
keyword parser is not only a stand-in -- it is also the fallback when the model call
fails, because failing to parse intent must never cost the player their turn.
"""

from __future__ import annotations

import logging
import re

from app.agents.ending import choose_ending
from app.agents.prompts import INTENT_SYSTEM, build_intent_prompt
from app.agents.safety import SafetyFilter
from app.content.world import World
from app.domain.direction import DecisionContext, DecisionKind, Directive, Pacing, Stance
from app.domain.enums import Risk, StepType
from app.domain.intent import PlayerIntent
from app.domain.state import CharacterState, GameSession
from app.llm.base import ChatProvider, LLMError
from app.llm.schema import strict_schema

log = logging.getLogger(__name__)

#: (action, patterns). First match wins; ordering encodes specificity.
_ACTION_LEXICON: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("confess", (r"\bi (?:really )?(?:love|like) (?:you|him|her|them)\b", r"\bconfess", r"\bfeelings for\b", r"\bkiss\b", r"\bask .* out\b", r"\bgo out with\b")),
    ("apologise", (r"\bsorry\b", r"\bapolog", r"\bmy fault\b", r"\bforgive\b", r"\bmake it up\b")),
    ("invite_character", (r"\bwalk home\b", r"\bcome with\b", r"\binvite\b", r"\bjoin me\b", r"\bwith me\b",
                          # "let's go" is an invitation; "let's go to the roof" is a move.
                          r"\blet'?s go\b(?!\s+to\b)", r"\btogether\b")),
    ("help", (r"\bhelp\b", r"\bcarry\b", r"\bcover for\b", r"\bstand up for\b", r"\bdefend\b", r"\bprotect\b")),
    ("compliment", (r"\byou look\b", r"\bcompliment\b", r"\bthank\b", r"\bproud of\b", r"\bimpress", r"\bamazing\b", r"\bgood at\b")),
    ("tease", (r"\btease\b", r"\bjoke\b", r"\bdare\b", r"\bbet you\b", r"\bidiot\b", r"\bstupid\b",
               r"\bmock\b", r"\binsult\b", r"\bhopeless\b", r"\buseless\b", r"\bpathetic\b",
               r"\bterrible at\b", r"\bcan'?t even\b", r"\bmake fun\b", r"\bwind (?:her|him|them) up\b")),
    ("move_location", (r"\bgo to\b", r"\bhead (?:to|for)\b", r"\bleave\b", r"\bwalk to\b", r"\bback to\b", r"\bgo home\b")),
    ("observe", (r"\bsay nothing\b", r"\bstay (?:quiet|silent)\b", r"\bwait\b", r"\bjust (?:watch|look|listen)\b", r"\bdo nothing\b")),
    ("ask_about", (r"\bask\b", r"\bwhy\b", r"\bwhat(?:'s| is)\b", r"\bhow come\b", r"\btell me\b", r"\bwho\b")),
)

_EMOTION_LEXICON: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("angry", (r"\bangr", r"\bshout\b", r"\byell\b", r"\bsnap\b", r"\bfurious\b")),
    ("affectionate", (r"\bgently\b", r"\bsoftly\b", r"\bwarmly\b", r"\blove\b", r"\bfondly\b", r"\bhold\b")),
    ("nervous", (r"\bnervous", r"\bhesitat", r"\bawkward", r"\bquietly\b", r"\bshy\b")),
    ("playful", (r"\bgrin\b", r"\blaugh", r"\bteas", r"\bjoke\b", r"\bplayful")),
    ("sincere", (r"\bhonest", r"\btruly\b", r"\bmean it\b", r"\bseriously\b")),
    ("sad", (r"\bsad\b", r"\bcry\b", r"\bupset\b", r"\bhurt\b")),
)

#: How each action reads in prose. Without this the narrator says things like
#: "Kai tries to invite character Aiko."
_ACTION_PHRASE: dict[str, str] = {
    "confess": "tell {who} the truth",
    "apologise": "apologise to {who}",
    "invite_character": "invite {who} along",
    "help": "help {who}",
    "compliment": "say something kind to {who}",
    "tease": "get under {who}'s skin",
    "move_location": "head for the {who}",
    "observe": "hold back and watch",
    "ask_about": "ask {who} something",
    "talk_to": "start a conversation with {who}",
}

_HIGH_RISK = {"confess", "tease"}
_MEDIUM_RISK = {"invite_character", "apologise", "help", "ask_about"}

_RISK_TENSION = {Risk.low: 20, Risk.medium: 45, Risk.high: 70}

#: Asking someone to come along names a place and a movement verb too, so it has to be
#: excluded explicitly -- "walk home with me" is an invitation, "let's go home" is a move.
_INVITATION = re.compile(r"\b(with me|with you|come with|join me|join us|together)\b", re.IGNORECASE)

#: Movement verbs. Paired with a named location these beat the keyword lexicon, because
#: pattern ordering cannot tell "let's go" (an invitation) from "let's go home" (a move)
#: without one rule per phrasing.
_MOVEMENT = re.compile(
    r"\b(go|going|goes|head|heading|walk|walking|leave|leaving|back to|over to|"
    r"see|visit|get to|make (?:my|our) way)\b",
    re.IGNORECASE,
)

#: What each arc is *for*. Keeps a long playthrough from becoming an undifferentiated
#: series of nice conversations.
_ARC_NOTES: dict[str, str] = {
    "prologue": (
        "everyone is still a first impression -- land one small, specific, unglamorous "
        "detail about somebody"
    ),
    "first_weeks": (
        "routines are forming; let someone show a habit, an obligation, or an irritation "
        "that predates the player"
    ),
    "festival": (
        "there is a deadline in the air; people are deciding who they want to be standing "
        "next to when it arrives"
    ),
    "summer": (
        "time is suddenly unstructured; what people do with the empty hours is the "
        "characterisation"
    ),
    "resolution": (
        "things said now are hard to unsay; let consequences from earlier arrive"
    ),
}


class DirectorAgent:
    def __init__(
        self,
        world: World,
        *,
        chat: ChatProvider | None = None,
        safety: SafetyFilter | None = None,
        temperature: float = 0.2,
        ending_min_steps: int = 300,
    ) -> None:
        self.world = world
        self.chat = chat
        self.safety = safety or SafetyFilter()
        self.temperature = temperature
        self.ending_min_steps = ending_min_steps

    async def parse(self, session: GameSession, raw: str) -> PlayerIntent:
        text = (raw or "").strip()
        if not text:
            return PlayerIntent(action="observe", risk=Risk.low, summary="", meaningful=False, raw=raw)

        usable, verdict = self.safety.screen_input(text)
        if not usable:
            # Absorbed in-world rather than rejected: the story continues, the attempt does not.
            log.info("player input screened out (%s)", verdict.reason)
            return PlayerIntent(
                action="observe",
                risk=Risk.low,
                summary="the moment passes without anything being said",
                meaningful=False,
                raw=text,
            )

        if self.chat is not None:
            try:
                return await self._parse_with_llm(session, text)
            except (LLMError, ValueError) as exc:
                log.warning("intent parse via LLM failed, using keyword parser: %s", exc)

        return self.parse_keywords(session, text)

    async def _parse_with_llm(self, session: GameSession, text: str) -> PlayerIntent:
        assert self.chat is not None
        payload = await self.chat.complete_json(
            system=INTENT_SYSTEM,
            user=build_intent_prompt(self.world, session, text),
            schema_name="player_intent",
            schema=strict_schema(PlayerIntent),
            max_tokens=400,
            temperature=self.temperature,
        )
        payload.pop("raw", None)
        intent = PlayerIntent.model_validate({**payload, "raw": text})
        intent.target = self.world.resolve_character(intent.target)
        if not intent.action.strip():
            intent.action = "talk_to"
        return intent

    def parse_keywords(self, session: GameSession, text: str) -> PlayerIntent:
        """Deterministic parser. Also the fallback when the model call fails."""
        lowered = text.lower()

        target = self._find_target(lowered, session)

        destination = self.world.resolve_location(lowered)
        if (
            destination
            and destination != session.world.location
            and _MOVEMENT.search(lowered)
            and not _INVITATION.search(lowered)
        ):
            # A named place plus a movement verb is a move, whatever else the sentence
            # happens to contain.
            action = "move_location"
        else:
            action = next(
                (
                    name
                    for name, patterns in _ACTION_LEXICON
                    if any(re.search(p, lowered) for p in patterns)
                ),
                "talk_to" if target else "observe",
            )
        emotion = next(
            (name for name, patterns in _EMOTION_LEXICON if any(re.search(p, lowered) for p in patterns)),
            None,
        )

        if action in _HIGH_RISK:
            risk = Risk.high
        elif action in _MEDIUM_RISK:
            risk = Risk.medium
        else:
            risk = Risk.low
        if emotion == "angry":
            risk = Risk.high

        if action == "move_location":
            place = self.world.location(destination) if destination else None
            who = place.in_prose if place else "somewhere else"
        elif target:
            who = self.world.character(target).name.split()[0]
        else:
            who = "everyone"

        template = _ACTION_PHRASE.get(action, action.replace("_", " ") + " {who}")
        summary = f"{{player}} tries to {template.format(who=who)}".strip()

        return PlayerIntent(
            action=action,
            target=target,
            emotion=emotion,
            risk=risk,
            summary=summary,
            meaningful=True,
            raw=text,
        )

    # -- planning ------------------------------------------------------------------------

    def plan(
        self,
        session: GameSession,
        intent: PlayerIntent,
        decision: DecisionContext,
        *,
        max_steps: int = 10,
    ) -> Directive:
        """Decide the *shape* of the next run before anything writes a word of it.

        Deterministic and model-free on purpose (PRD §33). This is the engine directing;
        handing "what should happen next" to the LLM as well would leave nothing owning
        pacing across a whole playthrough.
        """
        focus = self._focus(session, intent)
        stances = [
            self._stance(session.characters[cid], intent)
            for cid in focus
            if cid in session.characters
        ]

        tension = self._tension(session, intent, decision, stances)
        pacing = self._pacing(session, tension)

        # Only the character the attempt is AIMED at decides whether it lands. Letting
        # any bystander's stance veto it meant a warm invitation to Aiko failed because
        # Haruto happened to be standing nearby and does not know the player yet.
        lead = intent.target or (focus[0] if focus else None)
        lead_stance = next((stance for stance in stances if stance.character == lead), None)
        allow_failure = (
            intent.risk is Risk.high
            or tension >= 70
            or (lead_stance is not None and not lead_stance.receptive)
        )

        finale = self._finale_due(session, decision)
        ending_kind, ending_partner = (None, None)
        if finale:
            kind, partner = choose_ending(self.world, session)
            ending_kind, ending_partner = kind.value, partner

        return Directive(
            pacing=pacing,
            tension=tension,
            focus=focus,
            stances=stances,
            beat_goal=self._beat_goal(decision, pacing, allow_failure, intent),
            allow_failure=allow_failure and not finale,
            push_location=None if finale else self._push_location(session, pacing),
            arc_note=_ARC_NOTES.get(session.world.arc, ""),
            style_note=session.style.note(),
            max_steps=max_steps,
            is_finale=finale,
            ending_kind=ending_kind,
            ending_partner=ending_partner,
        )

    def _finale_due(self, session: GameSession, decision: DecisionContext) -> bool:
        """Has this playthrough earned its ending?

        The gate counts DELIVERED steps, not generated ones: a queue the player never read
        must not end their story. It also refuses on an ``auto`` turn, so a story never
        closes itself while the player is idle -- the ending should answer something they
        actually did.
        """
        if session.ended:
            return False
        if decision.kind is DecisionKind.auto:
            return False
        return (session.cursor + 1) > self.ending_min_steps

    def _focus(self, session: GameSession, intent: PlayerIntent) -> list[str]:
        """Who should carry this run: the target first, then whoever is standing there."""
        ordered: list[str] = []
        if intent.target:
            ordered.append(intent.target)
        ordered.extend(c for c in session.world.present_characters if c in session.characters)
        if not ordered:
            # Nobody present: fall back to whoever the player knows best, so a dry scene
            # still has someone in it.
            known = sorted(
                session.characters.values(),
                key=lambda state: state.value("familiarity"),
                reverse=True,
            )
            ordered = [state.id for state in known[:1]]
        return list(dict.fromkeys(ordered))[:3]

    @staticmethod
    def _stance(state: CharacterState, intent: PlayerIntent) -> Stance:
        """PRD §15: the same action means different things at different relationships."""
        affection = state.value("affection")
        trust = state.value("trust")
        anger = state.value("anger")
        romance = state.value("romance")
        familiarity = state.value("familiarity")

        if familiarity < 15 and trust < 20:
            return Stance(
                character=state.id,
                posture="still effectively a stranger to the player",
                note=(
                    f"familiarity {familiarity}, trust {trust} -- polite, uninvested, and "
                    "unlikely to volunteer anything"
                ),
                conflict_mode="cold",
                receptive=False,
            )

        if anger >= 25:
            return Stance(
                character=state.id,
                posture="still carrying something from earlier",
                note=f"anger {anger} -- warmth has to get past that first",
                conflict_mode="serious",
                receptive=False,
            )

        if trust < 25 and familiarity < 45:
            return Stance(
                character=state.id,
                posture="guarded",
                note=f"trust {trust} -- deflects direct questions, answers the easy half",
                conflict_mode="serious",
                receptive=False,
            )

        if trust < 25:
            # Familiar but still not trusting. Without this branch the relationship system
            # deadlocks: low trust makes every attempt fail, and a failed attempt earns no
            # trust, so a player can spend three hundred steps on someone and move nothing
            # but familiarity. Time spent together has to be a way in.
            return Stance(
                character=state.id,
                posture="thawing, in their own time",
                note=(
                    f"familiarity {familiarity} against trust {trust} -- you have been "
                    "around long enough that the guard is habit rather than judgement"
                ),
                conflict_mode="playful" if affection >= 25 else "serious",
            )

        if romance >= 55 and affection >= 45:
            return Stance(
                character=state.id,
                posture="reading more into gestures than they would admit",
                note=f"romance {romance}, affection {affection} -- nothing here is casual any more",
                conflict_mode="playful",
            )

        if affection >= 50 and trust >= 45:
            return Stance(
                character=state.id,
                posture="comfortable enough to tease",
                note=f"affection {affection}, trust {trust} -- teasing reads as fondness, not attack",
                conflict_mode="playful",
            )

        return Stance(
            character=state.id,
            posture="warming up, but not there yet",
            note=f"affection {affection}, trust {trust} -- willing, still deciding how much",
            conflict_mode="playful" if affection >= 30 else "serious",
        )

    @staticmethod
    def _tension(
        session: GameSession,
        intent: PlayerIntent,
        decision: DecisionContext,
        stances: list[Stance],
    ) -> int:
        tension = _RISK_TENSION.get(intent.risk, 45)
        for stance in stances:
            state = session.characters.get(stance.character)
            if state is None:
                continue
            tension += state.value("anger") // 3
            tension += state.value("jealousy") // 4
            tension -= state.value("trust") // 5
        if decision.kind is DecisionKind.free_text and intent.risk is Risk.high:
            # They typed it themselves rather than picking it off a menu.
            tension += 10
        if decision.kind is DecisionKind.auto:
            tension -= 20
        return max(0, min(100, tension))

    @staticmethod
    def _beats_since(session: GameSession, kinds: tuple[StepType, ...]) -> int:
        for offset, step in enumerate(reversed(session.steps)):
            if step.type in kinds:
                return offset
        return len(session.steps)

    def _pacing(self, session: GameSession, tension: int) -> Pacing:
        previous = session.last_directive.pacing if session.last_directive else None
        if previous is Pacing.charged and tension < 72:
            # Never two charged runs back to back: the quiet beat after is what makes
            # the loud one mean anything.
            return Pacing.release
        if tension >= 72:
            return Pacing.charged
        if tension >= 45:
            return Pacing.building
        if self._beats_since(session, (StepType.transition, StepType.event)) >= 14:
            return Pacing.building
        return Pacing.quiet

    def _push_location(self, session: GameSession, pacing: Pacing) -> str | None:
        """Suggest a move when the scene has been standing still (PRD §24 Rule 3)."""
        if pacing is Pacing.charged:
            return None  # never interrupt the peak with a scene change
        if self._beats_since(session, (StepType.transition,)) < 12:
            return None

        options = [
            location
            for location in self.world.locations
            if location.id != session.world.location
            and (not location.times or session.world.time_of_day in location.times)
        ]
        if not options:
            return None
        # Deterministic, so a replayed session moves the same way.
        return options[len(session.steps) % len(options)].id

    @staticmethod
    def _beat_goal(
        decision: DecisionContext, pacing: Pacing, allow_failure: bool, intent: PlayerIntent
    ) -> str:
        if decision.kind is DecisionKind.opening:
            return "introduce the place and the people, and end on a real question"
        if decision.kind is DecisionKind.auto:
            return "hold the moment without advancing it, then hand control straight back"

        by_pacing = {
            Pacing.quiet: (
                "stay small. One person, one honest exchange, no new complication"
            ),
            Pacing.building: (
                "let the attempt land and change something modest -- an admission, an "
                "obligation, a plan"
            ),
            Pacing.charged: (
                "this is the beat that costs something. Do not soften it, and do not "
                "resolve it inside this run"
            ),
            Pacing.release: (
                "come down from the last beat. Aftermath, not escalation -- what people "
                "do with themselves once the moment has passed"
            ),
        }
        goal = by_pacing[pacing]
        if allow_failure:
            goal += ", and it is fine if the attempt is not met the way they hoped"
        if intent.risk is Risk.high:
            goal += ". They are exposed here; treat that seriously"
        return goal

    def _find_target(self, lowered: str, session: GameSession) -> str | None:
        for character in self.world.characters:
            first = character.name.split()[0].lower()
            if re.search(rf"\b{re.escape(first)}\b", lowered) or re.search(
                rf"\b{re.escape(character.id)}\b", lowered
            ):
                return character.id

        present = [c for c in self.world.character_ids if c in session.world.present_characters]

        # No name given. "I say sorry" almost always means sorry to whoever you were
        # just talking to -- picking someone else because they happen to be in the room
        # reads as the game losing the thread.
        for step in reversed(session.steps[-12:]):
            speaker = step.dialogue.speaker if step.dialogue else None
            if speaker and speaker in present:
                return speaker

        return present[0] if len(present) == 1 else None
