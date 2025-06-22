"""
validate_policies.py  ─  Vérifie :
  1. La validité schématique de chaque *.yml dans /static/agents/templates
  2. La présence du template Jinja2 correspondant : /static/agents/prompts/prompt_<agent>.j2
Usage :
  python validate_policies.py app/static/agents/templates
"""

import os
import sys
import yaml
from pathlib import Path
from typing import Optional, List
from pydantic import BaseModel, Field, ValidationError, model_validator

# ────────────────────────────────────────────────────────────────────────────────
#  Modèles Pydantic minimalistes pour la validation syntaxique
# ────────────────────────────────────────────────────────────────────────────────
class Action(BaseModel):
    suggest_action: str
    route_to: Optional[str] = None


class Step(BaseModel):
    if_: Optional[str] = Field(default=None, alias="if")
    elif_: Optional[str] = Field(default=None, alias="elif")
    else_: Optional[bool] = Field(default=None, alias="else")
    say: str
    actions: Optional[List[Action]] = Field(default_factory=list)

    # exactement un seul des trois doit être défini
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


# ────────────────────────────────────────────────────────────────────────────────
#  Répertoires
# ────────────────────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent  # <projet>/app/...
STATIC_DIR = BASE_DIR / "static"
TEMPLATE_DIR = STATIC_DIR / "agents" / "templates"   # YAML policies
PROMPT_DIR = STATIC_DIR / "agents" / "prompts"       # prompt_*.j2

# ────────────────────────────────────────────────────────────────────────────────
#  Validation helpers
# ────────────────────────────────────────────────────────────────────────────────
def validate_prompt_exists(agent_name: str) -> bool:
    prompt_path = PROMPT_DIR / f"prompt_{agent_name}.j2"
    if not prompt_path.exists():
        print(f"   ⚠️  Missing prompt: {prompt_path}")
        return False
    return True


def validate_policy_file(filepath: Path) -> bool:
    ok = True
    try:
        data = yaml.safe_load(filepath.read_text(encoding="utf-8"))
        Policy(**data)                       # validation Pydantic
        agent_name = filepath.stem
        if validate_prompt_exists(agent_name):
            print(f"   ✅ {filepath.name} is valid ✓")
        else:
            ok = False
    except (ValidationError, yaml.YAMLError) as e:
        print(f"   ❌ {filepath.name} invalid:\n{e}")
        ok = False
    return ok


def validate_all_policies(directory: Path) -> None:
    print(f"🔍 Validating YAML policies in: {directory}")
    has_error = False

    for file in sorted(directory.glob("*.yml")):
        print(f" ─ {file.name}")
        if not validate_policy_file(file):
            has_error = True

    if has_error:
        print("❌ Validation finished with errors.")
        sys.exit(1)

    print("🎉 All policies and prompts are valid!")


# ────────────────────────────────────────────────────────────────────────────────
#  Entrée CLI
# ────────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Validate all AI policy YAMLs + prompt templates")
    parser.add_argument("directory", nargs="?", default=str(TEMPLATE_DIR),
                        help="Path to policy directory (default: static/agents/templates)")
    args = parser.parse_args()

    try:
        validate_all_policies(Path(args.directory))
    except Exception as exc:
        print(f"🔥 Fatal error: {exc}")
        sys.exit(1)
