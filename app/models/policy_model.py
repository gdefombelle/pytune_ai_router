from typing import Any, Dict, List, Optional, Literal, Union
from pydantic import BaseModel, Field, field_validator, validator


class Trigger(BaseModel):
    event: str
    condition: Optional[str]


class Action(BaseModel):
    suggest_action: str
    route_to: str


class ConversationStep(BaseModel):
    if_: Optional[str] = Field(None, alias="if")
    elif_: Optional[str] = Field(None, alias="elif")
    else_: Optional[bool] = Field(None, alias="else")
    say: Optional[str]
    actions: Optional[List[Action]]

    @field_validator('actions', mode="before")
    @classmethod
    def validate_actions(cls, v):
        if v is None:
            return []
        if isinstance(v, dict):
            return [v]  # 🔥 Correction : si dict => mettre dans une liste
        return v

    def validate_structure(self):
        if not (self.if_ or self.elif_ or self.else_):
            raise ValueError("Each conversation step must have 'if', 'elif' or 'else'")
        if not self.say:
            raise ValueError("Each step must include 'say'")
class Metadata(BaseModel):
    version: str
    lang: str
    allow_interruptions: bool = True

class Policy(BaseModel):
    name: str
    description: str
    triggers: List[Trigger]
    context: Optional[Dict[str, Any]] = None   # 🔥 ici
    conversation: List[ConversationStep]
    metadata: Metadata

class AgentResponse(BaseModel):
    message: str
    actions: Optional[List[dict]] = []
    meta: Optional[dict] = {}
