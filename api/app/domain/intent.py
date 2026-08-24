"""Player intent — PRD §8 Method B.

The player types prose; the Director Agent turns it into a bounded action. The player
states an *attempt*, never an *outcome* — the Story Agent decides what actually happens.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from app.domain.enums import Risk


class PlayerIntent(BaseModel):
    model_config = ConfigDict(extra="ignore")

    action: str = Field(description="snake_case verb, e.g. invite_character, confess, apologise")
    target: str | None = Field(default=None, description="character id the action is aimed at")
    emotion: str | None = Field(default=None, description="how the player is acting, e.g. affectionate")
    risk: Risk = Risk.medium
    summary: str = Field(default="", description="one clause restating the attempt in third person")
    meaningful: bool = Field(
        default=True,
        description="False for chatter that should not trigger a full generation cycle",
    )
    raw: str = ""
