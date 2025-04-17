from typing import List, Optional, Literal, Union
from pydantic import BaseModel, Field


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
    context: dict
    conversation: List[ConversationStep]
    metadata: Metadata
