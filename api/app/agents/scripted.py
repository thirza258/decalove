"""The scripted narrator.

This module earns its place twice:

1. It is the **offline provider** — the game is fully playable with no API key, which is
   what makes local development and the test suite possible.
2. It is the **failure fallback** of PRD §26 — when the real LLM errors, times out, or
   returns something the validator cannot repair, the story continues from here instead
   of the game dying.

It is deterministic: the same session state and the same input always produce the same
run, seeded from ``(session.id, step count)``.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from app.content.world import Character, World
from app.domain.direction import Directive, Stance
from app.domain.enums import RELATIONSHIP_AXES, StepType
from app.domain.intent import PlayerIntent
from app.domain.state import GameSession
from app.domain.story import (
    Choice,
    DialogueLine,
    GeneratedRun,
    GeneratedStep,
    MemoryProposal,
    RelationshipDelta,
    VisualSpec,
)

GENERIC = "_"


@dataclass(frozen=True)
class Beat:
    """One authored narrative family."""

    approach: tuple[str, ...]
    reply: dict[str, tuple[str, ...]]
    followup: tuple[str, ...]
    emotion: str
    delta: dict[str, int] = field(default_factory=dict)
    memory: str = ""
    importance: float = 0.4
    choices: tuple[str, ...] = ()


#: action keyword -> family. First match wins, so order matters.
FAMILY_KEYWORDS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("confess", ("confess", "love", "kiss", "romantic", "date", "feelings", "crush")),
    ("apologise", ("apolog", "sorry", "amends", "forgive", "make_up")),
    ("invite", ("invite", "ask_out", "walk_home", "join", "accompany", "together", "offer_to")),
    ("compliment", ("compliment", "praise", "flatter", "admire", "thank", "reassure", "encourage")),
    ("help", ("help", "assist", "support", "defend", "protect", "carry", "cover_for")),
    ("tease", ("tease", "joke", "provoke", "challenge", "dare", "insult", "mock", "argue")),
    ("move", ("go_to", "move", "leave", "travel", "head", "walk_to", "enter", "exit", "return")),
    ("observe", ("observe", "look", "wait", "watch", "think", "listen", "notice", "rest")),
    ("ask", ("ask", "question", "inquire", "discuss", "learn", "talk_about", "confront")),
)

BEATS: dict[str, Beat] = {
    "talk": Beat(
        approach=(
            "{Target} looks up as {player} comes over, and whatever was on {t_their} mind goes carefully away.",
            "{player} says {t_their} name. {Target} turns, half a beat slower than usual.",
            "There is a pause where {Target} decides how much of {t_themself} to bring to this.",
        ),
        reply={
            "aiko": ("Oh — {player}. I was just... never mind. Did you need something?",),
            "ren": ("Well, well. To what do I owe.",),
            "mika": ("Hey! You! Good, I was getting bored.",),
            "haruto": ("Mm.",),
            GENERIC: ("Hey.", "You needed me?"),
        },
        followup=(
            "It is not much of a conversation yet. It is a start.",
            "The silence afterwards is the comfortable kind, mostly.",
        ),
        emotion="neutral",
        delta={"familiarity": 1},
        memory="{player} sought {target} out with nothing in particular to say.",
        importance=0.2,
        choices=(
            "Ask how they've been.",
            "Say nothing and stay a while.",
            "Change the subject entirely.",
            "Ask what they were doing before you turned up.",
        ),
    ),
    "invite": Beat(
        approach=(
            "{Target} goes very still, the way people do when they are recalculating.",
            "The invitation lands. {Target} looks at {player} as though checking for a trick.",
            "For a second {Target} does not answer, and the {place} gets very loud.",
        ),
        reply={
            "aiko": (
                "You're — you're serious. You're actually asking.",
                "I have council work. I could... move it. Possibly.",
            ),
            "ren": (
                "Huh. Yeah, okay. I had nothing better going on. Obviously.",
                "You know I'm going to say yes. Ask me properly.",
            ),
            "mika": (
                "Yes! Obviously yes, why are you even doing the face?",
                "Finally. I've been waiting for someone to suggest something.",
            ),
            "haruto": (
                "...Now?",
                "I was going that way anyway. That's not a yes. It's adjacent to one.",
            ),
            GENERIC: ("If you want.", "All right. Lead the way."),
        },
        followup=(
            "Something in the shape of the afternoon changes.",
            "{Target} falls into step, half a pace behind, then level.",
        ),
        emotion="surprised",
        delta={"affection": 2, "familiarity": 2, "romance": 1},
        memory="{player} invited {target} along, and {target} said yes.",
        importance=0.6,
        choices=(
            "Walk in comfortable silence.",
            "Ask what they were really doing.",
            "Make them laugh.",
            "Take the long way.",
        ),
    ),
    "confess": Beat(
        approach=(
            "{Target} does not move. That is somehow worse than any answer.",
            "The words are out. {Target} looks at {player} like a page {t_they} cannot finish reading.",
            "{Target} draws a breath and holds it a moment too long.",
        ),
        reply={
            "aiko": (
                "You should not say things like that unless you mean them. I would — I would believe you.",
            ),
            "ren": ("Okay. Okay. Give me a second. I'm usually the one who says the disarming thing.",),
            "mika": ("You picked the worst possible timing and I love that about you. Say it again.",),
            "haruto": ("I heard you the first time. I'm just — deciding what to do with it.",),
            GENERIC: ("I don't know what to say.",),
        },
        followup=(
            "{Target} moves closer, waiting to see what {player} will do.",
            "Whatever happens next, it is not going to un-happen.",
        ),
        emotion="embarrassed",
        delta={"romance": 4, "affection": 3, "trust": 2},
        memory="{player} told {target} how {p_they} felt, out loud, without hedging.",
        importance=0.95,
        choices=(
            "Hold their gaze.",
            "Give them room to answer.",
            "Apologise for the timing.",
            "Say it again, slower.",
            "Leave before they answer.",
        ),
    ),
    "compliment": Beat(
        approach=(
            "{Target} was not braced for that one.",
            "The compliment goes in sideways, past every defence {Target} keeps up.",
            "{Target} blinks, and the composure takes a second to come back online.",
        ),
        reply={
            "aiko": ("That is — thank you. People usually notice the work, not the... thank you.",),
            "ren": ("Careful. Say things like that and I'll start believing them.",),
            "mika": ("Right?! I KNOW. Say it louder, Haruto's over there.",),
            "haruto": ("You don't have to do that.",),
            GENERIC: ("Thanks. Really.",),
        },
        followup=("{Target} does not quite meet {player}'s eyes for a moment.",),
        emotion="embarrassed",
        delta={"affection": 2, "trust": 1},
        memory="{player} said something kind to {target} and meant it.",
        importance=0.5,
        choices=("Let it sit.", "Push a little further.", "Move on before it gets awkward."),
    ),
    "apologise": Beat(
        approach=(
            "{Target} listens all the way to the end without interrupting, which is not nothing.",
            "The apology takes longer to say than {player} expected.",
        ),
        reply={
            "aiko": ("I had already decided not to mind. You've made that harder.",),
            "ren": ("You didn't have to do that. ...Thanks for doing that.",),
            "mika": ("Ugh. Fine! Fine. We're fine. Don't make it a whole thing.",),
            "haruto": ("Noted.",),
            GENERIC: ("Okay. Thank you.",),
        },
        followup=("Something that was pulled tight lets go, a little.",),
        emotion="thoughtful",
        delta={"trust": 3, "anger": -3, "respect": 1},
        memory="{player} apologised to {target} first.",
        importance=0.65,
        choices=(
            "Ask if you can start over.",
            "Say nothing else.",
            "Ask what they actually needed.",
            "Admit the whole of it.",
        ),
    ),
    "help": Beat(
        approach=(
            "{player} does not ask permission first, which turns out to be the correct call.",
            "{Target} starts to say it is fine, and then stops.",
        ),
        reply={
            "aiko": ("I could have managed. ...I'm glad I didn't have to.",),
            "ren": ("Huh. People don't usually stick around for this part.",),
            "mika": ("Okay, that was actually clutch. You're on my list now. The good one.",),
            "haruto": ("You didn't have to. Thank you.",),
            GENERIC: ("Thanks. I mean it.",),
        },
        followup=("Between the two of them it takes half the time.",),
        emotion="grateful",
        delta={"trust": 3, "respect": 2, "affection": 1},
        memory="{player} stepped in and helped {target} without being asked.",
        importance=0.8,
        choices=(
            "Ask what else needs doing.",
            "Ask why they didn't ask for help.",
            "Let them off the hook.",
            "Keep working in silence.",
        ),
    ),
    "tease": Beat(
        approach=(
            "{Target} narrows {t_their} eyes. The temperature drops one degree, playfully.",
            "That was a direct hit, and everyone present knows it.",
        ),
        reply={
            "aiko": ("I am going to remember that. I keep records.",),
            "ren": ("Oh, we're doing this? Great. I'm undefeated.",),
            "mika": ("HA! Okay, okay — round two, I'm ready this time.",),
            "haruto": ("...That was good. I hate that it was good.",),
            GENERIC: ("Very funny.",),
        },
        followup=("It is the kind of argument that leaves people closer than it found them.",),
        emotion="amused",
        delta={"familiarity": 3, "friendship": 2, "affection": 1},
        memory="{player} and {target} traded insults and both enjoyed it.",
        importance=0.4,
        choices=(
            "Push your luck.",
            "Concede gracefully.",
            "Change tack completely.",
            "Say the kind thing instead.",
        ),
    ),
    "ask": Beat(
        approach=(
            "{Target} considers the question longer than the question deserves.",
            "It is a simple thing to ask. {Target} does not treat it like one.",
        ),
        reply={
            "aiko": ("That's... a bigger question than you meant it to be, I think.",),
            "ren": ("Depends who's asking. It's you, so — maybe.",),
            "mika": ("Straight answer? Okay. You asked for it.",),
            "haruto": ("Why do you want to know?",),
            GENERIC: ("I'll think about how to answer that.",),
        },
        followup=("The answer, when it comes, is not quite the one on offer.",),
        emotion="thoughtful",
        delta={"trust": 2, "familiarity": 1},
        memory="{player} asked {target} something {t_they} does not usually get asked.",
        importance=0.55,
        choices=(
            "Wait for the real answer.",
            "Let them dodge it.",
            "Answer the same question yourself.",
            "Ask the harder version.",
        ),
    ),
    "move": Beat(
        approach=(
            "The {place} empties out behind them.",
            "It is a short walk, and nobody fills it with anything.",
        ),
        reply={GENERIC: ("Lead on.", "Right behind you.")},
        followup=("Somewhere else, the afternoon is still going.",),
        emotion="neutral",
        delta={"familiarity": 1},
        memory="",
        importance=0.15,
        choices=("Keep going.", "Stop and look back.", "Say what's actually on your mind."),
    ),
    "observe": Beat(
        approach=(
            "Nothing much happens for a while, and it is the good kind of nothing.",
            "{player} lets the {place} be the {place} for a minute.",
        ),
        reply={GENERIC: ("...", "You're quiet today.")},
        followup=("It is easier to notice things when nobody is performing.",),
        emotion="calm",
        delta={},
        memory="",
        importance=0.1,
        choices=("Say what you noticed.", "Keep it to yourself.", "Go find someone."),
    ),
}

@dataclass(frozen=True)
class Rebuff:
    """What the same beat looks like when it does *not* land.

    Selected by the Director's stance (PRD §15): the same invitation is a warm yes at
    high trust and a polite deflection at low trust. Without this the offline narrator
    would be relentlessly agreeable and relationship state would be invisible.
    """

    approach: tuple[str, ...]
    reply: dict[str, tuple[str, ...]]
    followup: tuple[str, ...]
    emotion: str = "guarded"
    delta: dict[str, int] = field(default_factory=dict)
    choices: tuple[str, ...] = ()
    #: A rebuff is at least as memorable as a success -- often more so.
    memory: str = ""
    importance: float = 0.45


GENERIC_REBUFF = Rebuff(
    approach=(
        "{Target} takes a second longer than the question needed.",
        "Something closes, politely, before the sentence is finished.",
    ),
    reply={
        "aiko": ("That's kind of you. I'm fine, though. Really.",),
        "ren": ("Ha. Sure. Anyway --",),
        "mika": ("Uh-huh. Sure. Later, maybe.",),
        "haruto": ("...No.",),
        GENERIC: ("Maybe another time.",),
    },
    followup=("It is not a rejection, exactly. It is not a yes either.",),
    delta={"familiarity": 1},
    choices=("Let it go.", "Push, gently.", "Ask what you got wrong."),
    memory="{player} reached out to {target}, and {target} did not take it up.",
)

REBUFFS: dict[str, Rebuff] = {
    "invite": Rebuff(
        approach=(
            "{Target} looks at the invitation the way you look at a door you are not sure is yours.",
            "For a moment it seems like a yes. It resolves into something else.",
        ),
        reply={
            "aiko": ("I can't. There's -- the council. There's always the council.",),
            "ren": ("Tempting. Rain check. I mean it, actually.",),
            "mika": ("Can't today! Training. Ask me again though, seriously.",),
            "haruto": ("I walk on my own. It isn't personal.",),
            GENERIC: ("Not today.",),
        },
        followup=("The offer sits there between them, unclaimed.",),
        emotion="troubled",
        delta={"familiarity": 1},
        choices=(
            "Say it's fine.",
            "Ask what's really going on.",
            "Leave it alone.",
            "Offer again, differently.",
        ),
        memory="{player} invited {target} along and was turned down.",
        importance=0.55,
    ),
    "confess": Rebuff(
        approach=(
            "{Target} hears it. That is the worst part -- {t_they} definitely hears it.",
            "The words land in a room that was not ready for them.",
        ),
        reply={
            "aiko": ("Please don't. Not -- not yet. I'm not being cruel. I'm asking.",),
            "ren": ("Okay. Wow. I'm going to need you to give me a minute. Or a week.",),
            "mika": ("...Huh. That's -- huh. I don't have a joke for that one.",),
            "haruto": ("You should not have said that here.",),
            GENERIC: ("I don't know what to do with that.",),
        },
        followup=("Nothing breaks. Something is just very carefully set down.",),
        emotion="troubled",
        delta={"familiarity": 2, "trust": 1},
        choices=(
            "Apologise for the timing.",
            "Say you meant it anyway.",
            "Give them the room.",
            "Take it back.",
            "Wait, and say nothing at all.",
        ),
        memory="{player} told {target} the truth, and {target} could not answer it.",
        importance=0.95,
    ),
    "tease": Rebuff(
        approach=(
            "The joke does not land. It just sits there.",
            "{Target}'s expression does not move, which is its own answer.",
        ),
        reply={
            "aiko": ("Is that supposed to be funny.",),
            "ren": ("Yeah. Okay. Cheap shot.",),
            "mika": ("Wow. Okay. Noted.",),
            "haruto": ("Mm.",),
            GENERIC: ("Right.",),
        },
        followup=("It costs something small, and both of them know it.",),
        emotion="annoyed",
        delta={"anger": 2, "trust": -1},
        choices=("Apologise properly.", "Double down.", "Change the subject."),
        memory="{player} made a joke at {target}'s expense that did not land.",
        importance=0.6,
    ),
    "ask": Rebuff(
        approach=("The question is heard, considered, and set aside.",),
        reply={
            "aiko": ("That's not really something I talk about.",),
            "ren": ("Ooh, big question. Let's do a small one first.",),
            "mika": ("Nope! Next.",),
            "haruto": ("Why do you want to know?",),
            GENERIC: ("Some other time.",),
        },
        followup=("The subject changes itself.",),
        delta={"familiarity": 1},
        choices=("Take the hint.", "Ask a smaller question.", "Say why you asked."),
        memory="{player} asked {target} something {t_they} did not want to answer.",
    ),
    "apologise": Rebuff(
        approach=(
            "{Target} lets the apology finish before deciding what to do with it.",
            "It is the right thing to say. It is not, yet, enough.",
        ),
        reply={
            "aiko": ("You don't have to explain. I'd rather you didn't, honestly.",),
            "ren": ("Hey. It's fine. It's -- yeah. It's fine.",),
            "mika": ("Okay. Okay! Can we not do the whole thing about it?",),
            "haruto": ("Understood.",),
            GENERIC: ("Thanks for saying it.",),
        },
        followup=("Something is acknowledged. Nothing is quite mended.",),
        emotion="troubled",
        # Turned down, but not for nothing: apologising to someone who is not ready to
        # hear it is still how trust gets built back.
        delta={"anger": -2, "familiarity": 2, "trust": 1},
        choices=("Leave it there.", "Say what you actually meant.", "Ask what would help."),
        memory="{player} apologised to {target}, and {target} did not want to discuss it.",
        importance=0.5,
    ),
    "compliment": Rebuff(
        approach=("The compliment glances off something and keeps going.",),
        reply={
            "aiko": ("You don't have to say things like that.",),
            "ren": ("Flattery. Bold strategy.",),
            "mika": ("Ha! Sure. Thanks.",),
            "haruto": ("Mm.",),
            GENERIC: ("If you say so.",),
        },
        followup=("It is not that {t_they} did not hear it. It is that it did not stick.",),
        delta={"familiarity": 2, "affection": 1},
        choices=("Say it again, properly.", "Let it drop.", "Ask why that landed badly."),
        memory="{player} said something kind to {target}, who did not take it in.",
    ),
    "talk": Rebuff(
        approach=(
            "{Target} answers, and the conversation does not go anywhere after that.",
            "There is a reply. There is not an opening.",
        ),
        reply={
            "aiko": ("Was there something you needed? Only I'm in the middle of this.",),
            "ren": ("Mm-hm. Yep. Anyway.",),
            "mika": ("Oh -- hey. Busy. Later?",),
            "haruto": ("...",),
            GENERIC: ("Hm.",),
        },
        followup=("Not every attempt at a conversation becomes one.",),
        delta={"familiarity": 1},
        choices=("Try a different way in.", "Let them be.", "Ask what's wrong."),
        memory="{player} tried to talk to {target}, who was not in the mood.",
        importance=0.2,
    ),
    "help": Rebuff(
        approach=("{Target} has the situation handled. Visibly. Determinedly.",),
        reply={
            "aiko": ("I've got it. I've always got it.",),
            "ren": ("Nah, you'd only make it worse. Affectionately.",),
            "mika": ("I can do it! ...I can do it.",),
            "haruto": ("Don't.",),
            GENERIC: ("I'm fine.",),
        },
        followup=("Watching someone refuse help is its own kind of information.",),
        delta={"familiarity": 2, "trust": 1},
        choices=("Stay anyway.", "Give them space.", "Point out they're struggling."),
        memory="{player} offered {target} help, and {target} refused it.",
    ),
}


#: The last run of the story, offline. Authored rather than generated because
#: ScriptedNarrator is also the failure fallback: if the finale could only be produced by
#: a working model, a timeout on the very last run would hand the player another choice
#: and the story would never end.
FINALE_APPROACH: dict[str, tuple[str, ...]] = {
    "romance": (
        "There is a version of this where neither of them says anything, and it is not this one.",
        "The year has been going somewhere the whole time. It arrives here.",
    ),
    "friendship": (
        "Nothing about this is dramatic. That is rather the point.",
        "Some things get decided without anyone announcing them.",
    ),
    "solo": (
        "The year winds down the way years do, without asking.",
        "There is no scene for this. There is just the end of it.",
    ),
}

FINALE_LINE: dict[str, dict[str, str]] = {
    "romance": {
        "aiko": "I had a whole speech. I wrote it down. ...I'm not going to need it, am I.",
        "ren": "Okay. Here's the thing I never say. I'd like to keep doing this. Whatever this is.",
        "mika": "You're slow, you know that? I've been waiting since like week two.",
        "haruto": "I've been reading the same page for ten minutes. I'd like you to know why.",
    },
    "friendship": {
        "aiko": "You made this year survivable. I don't say that to people. I'm saying it.",
        "ren": "You stuck around for the boring parts. Nobody does that.",
        "mika": "Same time next year, yeah? Don't make it weird. It's already weird.",
        "haruto": "I'll be here. That's -- that's the whole sentence.",
    },
}

FINALE_CLOSE: dict[str, tuple[str, ...]] = {
    "romance": (
        "The last train goes without them. Neither of them mentions it.",
        "Somewhere below, the town gets on with its evening. Up here, nobody is in a hurry.",
    ),
    "friendship": (
        "The gate closes behind them and the year is, quietly, over.",
        "They walk out together, arguing about something that does not matter at all.",
    ),
    "solo": (
        "The classroom empties. The window seat is free now, if you want it.",
        "Six weeks late, and somehow still early for whatever comes next.",
    ),
}


#: Pronoun expansion so the narrator never misgenders an authored character.
_PRONOUN_TABLE = {
    "she/her": ("she", "her", "her", "herself"),
    "he/him": ("he", "him", "his", "himself"),
    "they/them": ("they", "them", "their", "themself"),
}


def _pronouns(spec: str) -> tuple[str, str, str, str]:
    return _PRONOUN_TABLE.get(spec.strip().lower(), ("they", "them", "their", "themself"))


def classify(action: str) -> str:
    """Map a free-form action verb onto an authored beat family."""
    needle = (action or "").lower()
    for family, keywords in FAMILY_KEYWORDS:
        if any(keyword in needle for keyword in keywords):
            return family
    return "talk"


class ScriptedNarrator:
    """Deterministic template narrator over an authored world."""

    def __init__(self, world: World) -> None:
        self.world = world

    # -- public ------------------------------------------------------------------------

    def opening(self, session: GameSession) -> GeneratedRun:
        """The first run of a new game — PRD §30 opening scene."""
        rng = random.Random(f"{session.id}:opening")
        world = self.world
        location = world.location(session.world.location) or world.locations[0]
        cast = [c for c in world.characters if c.id in session.world.present_characters]
        if not cast:
            cast = list(world.characters[:2])
        first, second = (cast + list(world.characters))[:2]
        player = session.player.name

        steps: list[GeneratedStep] = [
            self._narration(
                location.id,
                f"{world.premise}",
                visual_character=None,
            ),
            self._narration(
                location.id,
                f"{location.description} {rng.choice(location.ambience or ('',))}".strip(),
            ),
            self._dialogue(
                location.id,
                first,
                self._opening_line(first, player),
                emotion=first.default_emotion,
                present=[c.id for c in cast],
            ),
            self._dialogue(
                location.id,
                second,
                self._opening_line(second, player, second=True),
                emotion=second.default_emotion,
                present=[c.id for c in cast],
            ),
        ]
        steps.append(
            self._choice_step(
                location.id,
                [c.id for c in cast],
                (
                    f"Introduce yourself properly to {first.name.split()[0]}.",
                    f"Say something to {second.name.split()[0]} instead.",
                    "Take the empty seat and keep your head down.",
                    "Apologise to the room for being six weeks late.",
                ),
                narration="Six weeks late, and the whole room is waiting to see what you do with it.",
            )
        )
        return GeneratedRun(steps=steps, summary=f"{player} arrived in {location.name} for the first time.")

    def finale(self, session: GameSession, directive: Directive) -> GeneratedRun:
        """The last run of the story. Terminates in a ``StepType.ending``."""
        rng = random.Random(f"{session.id}:finale")
        world = self.world
        location = world.location(session.world.location) or world.locations[0]
        player = session.player.name

        kind = directive.ending_kind or "solo"
        partner_id = directive.ending_partner
        partner = world.character(partner_id) if partner_id else None

        present = [partner.id] if partner else list(session.world.present_characters[:1])
        steps: list[GeneratedStep] = [
            self._narration(
                location.id,
                rng.choice(FINALE_APPROACH.get(kind, FINALE_APPROACH["solo"])),
                visual_character=partner.id if partner else None,
                present=present,
            )
        ]

        if partner:
            line = FINALE_LINE.get(kind, {}).get(partner.id)
            if line:
                steps.append(
                    self._dialogue(
                        location.id,
                        partner,
                        line,
                        emotion=partner.default_emotion,
                        present=present,
                    )
                )

        closing = rng.choice(FINALE_CLOSE.get(kind, FINALE_CLOSE["solo"]))
        steps.append(
            GeneratedStep(
                type=StepType.ending,
                location=location.id,
                characters=list(present),
                narration=f"{closing}\n\nThe end.",
                visual=self._visual(
                    location.id, partner.id if partner else None, partner.default_emotion if partner else None
                ),
            )
        )

        who = partner.name.split()[0] if partner else "nobody in particular"
        return GeneratedRun(steps=steps, summary=f"{player}'s story ended -- {kind}, with {who}.")

    def run(
        self,
        session: GameSession,
        intent: PlayerIntent,
        *,
        max_steps: int = 10,
        directive: Directive | None = None,
    ) -> GeneratedRun:
        """Generate one run: reaction beats, then a blocking decision.

        When the Director says the attempt is allowed to fail and the target is not
        receptive, the parallel rebuff bank is used instead -- so even offline, the same
        input plays differently at different relationship values.
        """
        world = self.world
        rng = random.Random(f"{session.id}:{len(session.steps)}:{intent.action}")

        family = classify(intent.action)
        beat = BEATS.get(family, BEATS["talk"])
        target = self._pick_target(session, intent, rng)
        destination = self._destination(session, intent, family, directive)
        stance = directive.stance_for(target.id) if (directive and target) else None
        rebuffed = bool(
            directive
            and directive.allow_failure
            and stance is not None
            and not stance.receptive
            # Walking somewhere and looking around are not offers anyone can decline;
            # rebuffing them produced lines like "I'm fine, though" in reply to a move.
            and family not in ("move", "observe")
        )
        rebuff = REBUFFS.get(family, GENERIC_REBUFF) if rebuffed else None
        location = world.location(session.world.location) or world.locations[0]
        present = list(dict.fromkeys([*session.world.present_characters, *( [target.id] if target else [] )]))

        player = session.player.name
        p_they, _p_them, _p_their, _p_themself = _pronouns(session.player.pronouns)
        if target:
            t_they, t_them, t_their, t_themself = _pronouns(target.pronouns)
            short = target.name.split()[0]
        else:
            t_they, t_them, t_their, t_themself = ("they", "them", "their", "themself")
            short = "everyone"

        def fill(template: str) -> str:
            # Templates come from authored beats *and* from LLM-written intent summaries,
            # which may contain stray braces. A failed substitution must never break a turn.
            try:
                return template.format(
                    player=player,
                    target=short,
                    Target=short,
                    place=location.in_prose,
                    p_they=p_they,
                    t_they=t_they,
                    t_them=t_them,
                    t_their=t_their,
                    t_themself=t_themself,
                )
            except (KeyError, IndexError, ValueError):
                return template

        steps: list[GeneratedStep] = []
        #: Beats that may be dropped to fit max_steps, most expendable first. The
        #: transition, the character's line and the consequence beat are not in here.
        droppable: list[GeneratedStep] = []

        if destination:
            # A real transition step, not just a relabelled narration: the engine only
            # moves the clock and the location when it sees one (PRD §24 Rule 3).
            moving_to = world.location(destination)
            steps.append(
                GeneratedStep(
                    type=StepType.transition,
                    location=destination,
                    characters=list(present),
                    narration=(
                        f"The {location.in_prose} empties out behind them. "
                        f"{moving_to.description}"
                        if moving_to
                        else f"The {location.in_prose} empties out behind them."
                    ),
                    visual=self._visual(destination, target.id if target else None),
                )
            )
            location = moving_to or location

        if intent.summary:
            restatement = self._narration(
                location.id,
                fill(intent.summary if intent.summary.endswith(".") else intent.summary + "."),
                visual_character=target.id if target else None,
                present=present,
            )
            steps.append(restatement)
            # The most expendable beat in the run: it restates what the player just did.
            droppable.append(restatement)

        approach = rebuff.approach if rebuff else beat.approach
        emotion = rebuff.emotion if rebuff else beat.emotion

        approach_step = self._narration(
            location.id,
            fill(rng.choice(approach)),
            visual_character=target.id if target else None,
            expression=emotion,
            present=present,
        )
        steps.append(approach_step)
        droppable.append(approach_step)

        if target:
            bank = rebuff.reply if rebuff else beat.reply
            lines = bank.get(target.id) or bank.get(GENERIC) or ("...",)
            steps.append(
                self._dialogue(
                    location.id,
                    target,
                    fill(rng.choice(lines)),
                    emotion=emotion,
                    present=present,
                )
            )

        follow = self._narration(
            location.id,
            fill(rng.choice(rebuff.followup if rebuff else beat.followup)),
            visual_character=target.id if target else None,
            expression=emotion,
            present=present,
        )
        delta = rebuff.delta if rebuff else beat.delta
        if target and delta:
            follow.relationship_changes = {target.id: RelationshipDelta(**delta)}
            follow.emotion = {target.id: emotion}
        memory_text = rebuff.memory if rebuff else beat.memory
        if target and memory_text:
            follow.memory = MemoryProposal(
                character=target.id,
                text=fill(memory_text),
                importance=rebuff.importance if rebuff else beat.importance,
                emotion=emotion,
            )
        steps.append(follow)

        choices = (rebuff.choices if rebuff else beat.choices) or BEATS["talk"].choices
        steps.append(
            self._choice_step(
                location.id,
                present,
                tuple(fill(c) for c in choices),
                character=target.id if target else None,
                expression=emotion,
            )
        )

        # Fit the run to max_steps by dropping the most expendable beats, never by
        # slicing. Slicing used to cut the decision point off the end and then overwrite
        # whatever was last -- which, on any run that also moved location, was the step
        # carrying the relationship delta and the memory. Moving somewhere silently cost
        # the player the consequences of what they had just done.
        body = steps[:-1]
        terminal = steps[-1]
        while len(body) + 1 > max_steps and any(step in droppable for step in body):
            for candidate in droppable:
                if candidate in body:
                    body.remove(candidate)
                    break

        steps = body + [terminal]
        if not steps[-1].is_blocking:  # never end a run without handing control back
            steps.append(self._choice_step(location.id, present, tuple(fill(c) for c in choices)))
            steps = steps[-max_steps:]

        who = short if target else "the room"
        outcome = "turned it down" if rebuff else "took it well enough"
        # This summary is replayed into later prompts as history, so it should read like
        # a sentence rather than like a log line.
        attempt = fill(intent.summary) if intent.summary else (
            f"{player} {intent.action.replace('_', ' ')}"
        )
        return GeneratedRun(steps=steps, summary=f"{attempt} — {who} {outcome}.")

    # -- step builders -----------------------------------------------------------------

    def _visual(
        self,
        location_id: str,
        character: str | None = None,
        expression: str | None = None,
    ) -> VisualSpec:
        location = self.world.location(location_id)
        return VisualSpec(
            background=location_id,
            character=character,
            expression=expression,
            time_of_day=(location.times[0] if location and location.times else None),
            mood="warm",
        )

    def _narration(
        self,
        location_id: str,
        text: str,
        *,
        visual_character: str | None = None,
        expression: str | None = None,
        present: list[str] | None = None,
    ) -> GeneratedStep:
        return GeneratedStep(
            type=StepType.narration,
            location=location_id,
            characters=list(present or ([visual_character] if visual_character else [])),
            narration=text,
            visual=self._visual(location_id, visual_character, expression),
        )

    def _dialogue(
        self,
        location_id: str,
        character: Character,
        text: str,
        *,
        emotion: str,
        present: list[str] | None = None,
    ) -> GeneratedStep:
        return GeneratedStep(
            type=StepType.dialogue,
            location=location_id,
            characters=list(present or [character.id]),
            dialogue=DialogueLine(speaker=character.id, text=text, emotion=emotion),
            emotion={character.id: emotion},
            visual=self._visual(location_id, character.id, emotion),
        )

    def _choice_step(
        self,
        location_id: str,
        present: list[str],
        options: tuple[str, ...],
        *,
        narration: str | None = None,
        character: str | None = None,
        expression: str | None = None,
    ) -> GeneratedStep:
        return GeneratedStep(
            type=StepType.choice,
            location=location_id,
            characters=list(present),
            narration=narration,
            next_choices=[
                Choice(id=f"choice_{i + 1}", text=text) for i, text in enumerate(options[:5])
            ],
            visual=self._visual(location_id, character, expression),
        )

    # -- helpers -----------------------------------------------------------------------

    def _destination(
        self,
        session: GameSession,
        intent: PlayerIntent,
        family: str,
        directive: Directive | None,
    ) -> str | None:
        """Where this run should move the scene, if anywhere."""
        if family == "move":
            named = self.world.resolve_location(intent.raw) or self.world.resolve_location(
                intent.target
            )
            if named and named != session.world.location:
                return named
        if directive and directive.push_location != session.world.location:
            return directive.push_location
        return None

    def _pick_target(
        self, session: GameSession, intent: PlayerIntent, rng: random.Random
    ) -> Character | None:
        explicit = self.world.resolve_character(intent.target)
        if explicit:
            return self.world.character(explicit)
        present = [
            character
            for character in self.world.characters
            if character.id in session.world.present_characters
        ]
        if present:
            return rng.choice(present)
        return None

    @staticmethod
    def _opening_line(character: Character, player: str, *, second: bool = False) -> str:
        first_name = character.name.split()[0]
        if second:
            return {
                "aiko": f"Sit anywhere. I'll bring you the handouts you've missed. All of them.",
                "ren": f"Six weeks in. Bold. I respect it.",
                "mika": f"New kid! Do you run? Please say you run.",
                "haruto": f"There's a spare desk by the window. It's the cold one.",
            }.get(character.id, f"Welcome to 2-B, {player}.")
        return {
            "aiko": f"You must be the transfer. I'm {first_name} — class representative. I'll get you caught up.",
            "ren": f"Oh good, a new face. This room was getting predictable.",
            "mika": f"HEY! You're the new one, right? I'm {first_name}. You're sitting with us.",
            "haruto": f"...You're in my light.",
        }.get(character.id, f"I'm {first_name}.")


def relationship_delta_dict(delta: RelationshipDelta) -> dict[str, int]:
    return {axis: value for axis, value in delta.as_dict().items() if value}


__all__ = ["ScriptedNarrator", "classify", "BEATS", "RELATIONSHIP_AXES", "relationship_delta_dict"]
