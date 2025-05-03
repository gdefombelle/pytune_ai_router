import os
import sys
import yaml
from typing import Optional, List, Literal
from pydantic import BaseModel, Field, model_validator, ValidationError


class Action(BaseModel):
    suggest_action: str
    route_to: Optional[str] = None


class Step(BaseModel):
    if_: Optional[str] = Field(default=None, alias="if")
    elif_: Optional[str] = Field(default=None, alias="elif")
    else_: Optional[bool] = Field(default=None, alias="else")
    say: str
    actions: Optional[List[Action]] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def check_one_condition(cls, data: dict):
        conditions = [data.get("if"), data.get("elif"), data.get("else")]
        if sum(c is not None for c in conditions) != 1:
            raise ValueError("Exactly one of 'if', 'elif', or 'else' must be defined in each step.")
        return data


class Policy(BaseModel):
    name: str
    description: str
    triggers: List[dict]
    context: dict
    conversation: List[Step]
    metadata: dict


def validate_policy_file(filepath: str):
    with open(filepath, "r", encoding="utf-8") as f:
        try:
            data = yaml.safe_load(f)
            Policy(**data)
            print(f"✅ {filepath} is valid.")
        except Exception as e:
            print(f"❌ Error in {filepath}: {e}")


def validate_all_policies(directory: str):
    print(f"🔍 Validating all YAML agent policies in: {directory}")
    for filename in os.listdir(directory):
        if filename.endswith(".yml") or filename.endswith(".yaml"):
            file_path = os.path.join(directory, filename)
            print(f"🔍 Checking {file_path}...")
            validate_policy_file(file_path)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Validate all AI policy YAMLs")
    parser.add_argument("validate", help="Path to policy directory (e.g., templates)")
    args = parser.parse_args()

    try:
        validate_all_policies(args.validate)
    except Exception as e:
        print(f"🔥 Fatal error: {e}")
        sys.exit(1)
