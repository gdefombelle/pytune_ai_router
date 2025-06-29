from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, field_validator


class Trigger(BaseModel):
    event: str
    condition: Optional[str]


class Action(BaseModel):
    suggest_action: Optional[str] = None
    route_to: Optional[str] = None
    trigger_event: Optional[str] = None
    params: Optional[Dict[str, Any]] = None

    @property
    def is_valid(self):
        return any([self.suggest_action, self.route_to, self.trigger_event])


class ConversationStep(BaseModel):
    if_: Optional[str] = Field(None, alias="if")
    elif_: Optional[str] = Field(None, alias="elif")
    else_: Optional[bool] = Field(None, alias="else")
    say: Optional[str]
    actions: List[Action] = []  # plus Optional

    @field_validator("actions", mode="before")
    @classmethod
    def normalize_actions(cls, v):
        if v is None:
            return []
        if isinstance(v, dict):
            return [v]
        if isinstance(v, list):
            return v
        raise ValueError("actions must be a list or a dict")

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
    context: Optional[Dict[str, Any]] = None
    conversation: List[ConversationStep]
    metadata: Metadata


class AgentResponse(BaseModel):
    message: str
    actions: list = []
    meta: dict = {}
    context_update: Optional[Dict[str, Any]] = None
    status :str = None
