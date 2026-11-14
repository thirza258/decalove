"""Character knowledge and belief — the intelligence PRD's FR-02.

World truth is not character knowledge. A character can only act on a fact they
witnessed, were told, overheard, or could reasonably infer. The engine records the
acquisition and its source; the prompt is assembled per character from these records,
and a character with no record for a fact is told, in as many words, that they do not
know it.

Misconceptions are first-class: ``knowledge_type="misconception"`` says a character
believes something untrue, and nothing about the engine forces them to stop believing
it until a delivered event corrects it.
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class KnowledgeType(str, Enum):
    known = "known"
    believed = "believed"
    suspected = "suspected"
    misconception = "misconception"
    unknown = "unknown"


class AcquisitionMethod(str, Enum):
    witnessed = "witnessed"
    told_directly = "told_directly"
    overheard = "overheard"
    public_information = "public_information"
    inferred = "inferred"


#: Methods that let a character reference a fact as their own knowledge. ``unknown`` is
#: a deliberate absence and is never treated as knowing.
_KNOWING = frozenset({
    KnowledgeType.known,
    KnowledgeType.believed,
    KnowledgeType.suspected,
    KnowledgeType.misconception,
})


class CharacterKnowledge(BaseModel):
    """One character's relationship to one fact."""

    model_config = ConfigDict(extra="ignore")

    id: str
    game_id: str
    character_id: str

    #: Stable identity of the fact across the whole game. Two characters share a fact_id
    #: when they hold knowledge of the same event; their propositions may still differ.
    fact_id: str
    subject: str = ""
    proposition: str = ""

    knowledge_type: KnowledgeType = KnowledgeType.known
    confidence: float = 0.5

    acquisition_method: AcquisitionMethod = AcquisitionMethod.witnessed
    source_character_id: str | None = None
    source_step_id: str | None = None

    created_at_step: int = 0
    last_updated_step: int = 0
    metadata: dict = Field(default_factory=dict)

    @property
    def knows(self) -> bool:
        return self.knowledge_type in _KNOWING

    def render(self) -> str:
        return (
            f"{self.proposition} "
            f"({self.knowledge_type.value}, {self.acquisition_method.value}, "
            f"confidence {self.confidence:.2f})"
        )
