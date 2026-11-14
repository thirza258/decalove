"""Character knowledge and belief — the intelligence PRD's FR-02.

Acquisition is **engine-derived from delivered steps**, not requested from a model. That
is the only way to guarantee the rule the feature exists for: a character cannot know
something the engine never recorded them learning.

Rules (deterministic):

* A character present in a delivered step witnesses the beat.
* A dialogue line is ``told_directly`` when only the speaker and one listener are
  present; with more witnesses it is ``overheard``.
* A world event (a step carrying flags) is ``public_information`` for those present.
* A secret is disclosed when its own words appear in the owner's delivered dialogue;
  the other people in that scene then know it.
* Nobody learns anything from a step they were not in.

Knowledge is a *secondary read model*: a write failure costs context, never a beat, so
every call here is bounded and guarded by its caller.
"""

from __future__ import annotations

import logging
import re
import uuid

from app.content.world import World
from app.domain.knowledge import (
    AcquisitionMethod,
    CharacterKnowledge,
    KnowledgeType,
)
from app.domain.state import GameSession
from app.domain.story import StoryStep
from app.repositories.base import KnowledgeRepository

log = logging.getLogger(__name__)

#: Significant enough to count as evidence that a secret was spoken aloud.
_MIN_SECRET_TOKEN = 5
_SECRET_STOPWORDS = frozenset({
    "about", "after", "again", "against", "because", "before", "being", "between",
    "could", "every", "their", "there", "these", "thing", "think", "where", "which",
    "while", "would", "never", "still", "really", "something", "someone", "himself",
    "herself", "themselves", "player",
})

#: How many facts per character the prompt may carry. Knowledge grows with the ledger,
#: so what reaches a prompt is capped; the store keeps everything.
MAX_RENDERED_FACTS = 8


def fact_id_for_step(game_id: str, step_id: str) -> str:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"decalove:{game_id}:fact:{step_id}").hex


def secret_fact_id(game_id: str, character_id: str) -> str:
    return uuid.uuid5(
        uuid.NAMESPACE_URL, f"decalove:{game_id}:secret:{character_id}"
    ).hex


def knowledge_id(game_id: str, character_id: str, fact_id: str) -> str:
    return uuid.uuid5(
        uuid.NAMESPACE_URL, f"decalove:{game_id}:knows:{character_id}:{fact_id}"
    ).hex


def _tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9']+", (text or "").lower()) if len(t) > 2}


def _secret_tokens(secret: str) -> set[str]:
    return {
        token for token in _tokens(secret)
        if len(token) >= _MIN_SECRET_TOKEN and token not in _SECRET_STOPWORDS
    }


def _beat_text(step: StoryStep) -> str:
    if step.dialogue and step.dialogue.text.strip():
        return step.dialogue.text.strip()
    return (step.narration or "").strip()


def render_knowledge(
    world: World,
    knowledge: dict[str, list[CharacterKnowledge]],
    characters: list[str],
) -> str:
    """Per-character knowledge blocks for the prompt.

    A character with nothing listed knows nothing about this scene beyond what is in
    front of them, and the text says so explicitly -- silence reads as permission, which
    is exactly the leak this feature prevents. Absent characters are listed separately so
    the writer can see what an off-screen person is owed, without implying presence.
    """
    def name_of(character_id: str) -> str:
        character = world.character(character_id)
        return character.name if character else character_id

    lines: list[str] = []
    for character_id in characters:
        facts = knowledge.get(character_id, [])[-MAX_RENDERED_FACTS:]
        if not facts:
            lines.append(f"    - {name_of(character_id)}: no established knowledge "
                         "beyond this scene.")
            continue
        lines.append(f"    - {name_of(character_id)} knows:")
        lines.extend(
            f"        · {fact.proposition} ({fact.knowledge_type.value})" for fact in facts
        )
    for character_id in sorted(set(knowledge) - set(characters))[:4]:
        facts = knowledge[character_id][-3:]
        if facts:
            lines.append(
                f"    - {name_of(character_id)} (not present) knows: "
                + "; ".join(fact.proposition for fact in facts)
            )
    return "\n".join(lines) or "    - (nobody knows anything yet)"


class CharacterKnowledgeManager:
    """Retrieve, acquire and check what each character knows."""

    def __init__(self, repository: KnowledgeRepository, *, world: World) -> None:
        self.repository = repository
        self.world = world

    # -- reads ---------------------------------------------------------------------------

    async def retrieve(self, game_id: str, character_id: str) -> list[CharacterKnowledge]:
        records = await self.repository.for_game(game_id, character_id)
        return [record for record in records if record.knows]

    async def for_game(self, game_id: str) -> dict[str, list[CharacterKnowledge]]:
        records = await self.repository.for_game(game_id)
        grouped: dict[str, list[CharacterKnowledge]] = {}
        for record in records:
            if record.knows:
                grouped.setdefault(record.character_id, []).append(record)
        return grouped

    def render(self, knowledge: dict[str, list[CharacterKnowledge]], characters: list[str]) -> str:
        return render_knowledge(self.world, knowledge, characters)

    # -- acquisition ---------------------------------------------------------------------

    async def seed(self, game_id: str, session: GameSession) -> None:
        """Each character knows their own secret from the start. Idempotent."""
        for character in self.world.characters:
            if not character.secret:
                continue
            await self._acquire(
                game_id=game_id,
                character_id=character.id,
                fact_id=secret_fact_id(game_id, character.id),
                proposition=f"their own secret: {character.secret}",
                method=AcquisitionMethod.witnessed,
                knowledge_type=KnowledgeType.known,
                confidence=1.0,
                step_index=0,
                metadata={"own_secret": True},
            )

    async def acquire_from_step(
        self, session: GameSession, step: StoryStep
    ) -> list[CharacterKnowledge]:
        """Record what the people in a delivered step learned from it.

        Called on delivery, under the game lock, from the engine -- never from model
        output. Deterministic: replaying a step produces identical records.
        """
        present = [c for c in step.characters if self.world.character(c)]
        if not present:
            return []
        if not self._worth_recording(step):
            return []

        acquired: list[CharacterKnowledge] = []
        fact_id = fact_id_for_step(session.id, step.step_id)
        text = _beat_text(step)
        if not text:
            return []
        subject = step.dialogue.speaker if step.dialogue else ", ".join(present)
        listeners = len(present) - (1 if step.dialogue else 0)

        if step.dialogue:
            method = (
                AcquisitionMethod.told_directly
                if 0 < listeners <= 1
                else AcquisitionMethod.overheard
            )
        elif step.flags_set:
            method = AcquisitionMethod.public_information
        else:
            method = AcquisitionMethod.witnessed

        for character_id in present:
            if step.dialogue and step.dialogue.speaker == character_id:
                # The speaker knows their own line beyond doubt.
                speaker_method = AcquisitionMethod.witnessed
                confidence = 1.0
            else:
                speaker_method = method
                confidence = 0.9 if method is AcquisitionMethod.witnessed else 0.7
            acquired.append(
                await self._acquire(
                    game_id=session.id,
                    character_id=character_id,
                    fact_id=fact_id,
                    proposition=text,
                    method=speaker_method,
                    knowledge_type=KnowledgeType.known,
                    confidence=confidence,
                    step_index=step.index,
                    source_step_id=step.step_id,
                    source_character_id=step.dialogue.speaker if step.dialogue else None,
                )
            )

        # A secret spoken aloud is learned by everyone else in the scene.
        disclosure = self.disclosed_secret(step)
        if disclosure:
            owner, secret = disclosure
            secret_fid = secret_fact_id(session.id, owner)
            for character_id in present:
                if character_id == owner:
                    continue
                acquired.append(
                    await self._acquire(
                        game_id=session.id,
                        character_id=character_id,
                        fact_id=secret_fid,
                        proposition=f"{self._name(owner)}'s secret: {secret}",
                        method=(
                            AcquisitionMethod.told_directly
                            if len(present) <= 2 else AcquisitionMethod.overheard
                        ),
                        knowledge_type=KnowledgeType.known,
                        confidence=0.9,
                        step_index=step.index,
                        source_step_id=step.step_id,
                        source_character_id=owner,
                        metadata={"disclosure": True},
                    )
                )
        return acquired

    @staticmethod
    def _worth_recording(step: StoryStep) -> bool:
        """Not every buffered narration beat is a learnable fact.

        Dialogue, events, discoveries and state changes are; an atmospheric line about
        the weather is not. The filter keeps the knowledge store proportional to what
        the story actually establishes instead of to its word count.
        """
        return bool(
            step.dialogue
            or step.memory
            or step.flags_set
            or step.relationship_changes
            or step.type.value in ("event", "transition")
        )

    def disclosed_secret(self, step: StoryStep) -> tuple[str, str] | None:
        """``(owner_id, secret)`` when this step's dialogue speaks a character's secret."""
        if not step.dialogue:
            return None
        owner = self.world.character(step.dialogue.speaker)
        if owner is None or not owner.secret:
            return None
        wanted = _secret_tokens(owner.secret)
        if not wanted:
            return None
        spoken = _tokens(step.dialogue.text)
        overlap = len(wanted & spoken)
        if overlap / len(wanted) >= 0.5:
            return owner.id, owner.secret
        return None

    async def acquire(
        self,
        *,
        game_id: str,
        character_id: str,
        fact_id: str,
        proposition: str,
        method: AcquisitionMethod = AcquisitionMethod.inferred,
        knowledge_type: KnowledgeType = KnowledgeType.believed,
        confidence: float = 0.5,
        step_index: int = 0,
        source_step_id: str | None = None,
        source_character_id: str | None = None,
        metadata: dict | None = None,
    ) -> CharacterKnowledge:
        """Record a single acquisition the engine decided was permitted.

        Public for deliberate cases (a correction, a letter, a phone call) where the
        acquisition is not visible in a delivered scene. Delivery-derived acquisition
        should keep going through ``acquire_from_step``.
        """
        if self.world.character(character_id) is None:
            raise ValueError(f"unknown character {character_id!r}")
        return await self._acquire(
            game_id=game_id,
            character_id=character_id,
            fact_id=fact_id,
            proposition=proposition,
            method=method,
            knowledge_type=knowledge_type,
            confidence=confidence,
            step_index=step_index,
            source_step_id=source_step_id,
            source_character_id=source_character_id,
            metadata=metadata,
        )

    async def _acquire(
        self,
        *,
        game_id: str,
        character_id: str,
        fact_id: str,
        proposition: str,
        method: AcquisitionMethod,
        knowledge_type: KnowledgeType,
        confidence: float,
        step_index: int,
        source_step_id: str | None = None,
        source_character_id: str | None = None,
        metadata: dict | None = None,
    ) -> CharacterKnowledge:
        record = CharacterKnowledge(
            id=knowledge_id(game_id, character_id, fact_id),
            game_id=game_id,
            character_id=character_id,
            fact_id=fact_id,
            subject=character_id,
            proposition=proposition[:300],
            knowledge_type=knowledge_type,
            confidence=max(0.0, min(1.0, confidence)),
            acquisition_method=method,
            source_character_id=source_character_id,
            source_step_id=source_step_id,
            created_at_step=step_index,
            last_updated_step=step_index,
            metadata=metadata or {},
        )
        await self.repository.upsert(record)
        return record

    # -- claims --------------------------------------------------------------------------

    def validate_claim(
        self,
        character_id: str,
        claim: str,
        knowledge: list[CharacterKnowledge] | dict[str, list[CharacterKnowledge]],
    ) -> bool:
        """Whether a character may assert ``claim`` given what they know.

        Deliberately conservative and lexical: a claim is permitted when its content
        words are covered by at least one known fact. This is a guard rail for tests and
        a trace signal, not a semantic proof -- the prompt's knowledge boundaries are
        what stop the leak in practice.
        """
        if not claim.strip():
            return True
        if isinstance(knowledge, dict):
            facts = knowledge.get(character_id, [])
        else:
            facts = [fact for fact in knowledge if fact.character_id == character_id]
        wanted = {token for token in _tokens(claim) if len(token) > 3}
        if not wanted:
            return True
        for fact in facts:
            known = _tokens(fact.proposition)
            if wanted & known and len(wanted & known) / len(wanted) >= 0.4:
                return True
        return False

    def _name(self, character_id: str) -> str:
        character = self.world.character(character_id)
        return character.name if character else character_id
