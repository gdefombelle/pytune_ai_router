"""
validate_policies.py — Vérifie :
  1. La validité schématique de chaque *.yml dans /static/agents/templates
  2. La présence du template Jinja2 correspondant : /static/agents/prompts/prompt_<agent>.j2
  3. L'évaluation statique des context.variables et des conditions de scénario
Usage :
  python validate_policies.py app/static/agents/templates
"""

import sys
import yaml
from pathlib import Path
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, ValidationError, model_validator

# ─────────────── Modèles Pydantic ───────────────
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
    context: Dict[str, Any]
    conversation: List[Step]
    metadata: Dict[str, Any]

# ─────────────── Helpers dynamiques ───────────────
class DotDict(dict):
    def __getattr__(self, attr):
        val = self.get(attr)
        return DotDict(val) if isinstance(val, dict) else val
    def __getitem__(self, item):
        val = dict.__getitem__(self, item)
        return DotDict(val) if isinstance(val, dict) else val

def validate_policy_variables(policy: Policy, filename: str):
    flat_context = DotDict({
        "first_piano": {
            "brand": "Yamaha", "model": "U3", "category": "upright",
            "serial_number": "123456", "year_estimated": 1980,
            "size_cm": 131, "confirmed": True,
        },
        "user_profile": {
            "firstname": "Alice", "music_style": ["classical"], "skill_level": "intermediate",
        }
    })
    variables = policy.context.get("variables", {})
    for var_name, expression in variables.items():
        try:
            eval(expression, {}, flat_context)
        except Exception as e:
            print(f"   ⚠️  {filename} → Erreur dans la variable '{var_name}':\n      ✗ {expression}\n      → {type(e).__name__}: {e}")

def validate_conversation_conditions(policy: Policy, filename: str):
    mock_context = DotDict({
        "first_piano": {
            "brand": "Steinway", "model": "B", "category": "grand",
            "serial_number": "XYZ", "year_estimated": 1975,
            "size_cm": 211, "confirmed": False
        },
        "user_profile": {
            "music_style": ["jazz"], "skill_level": "advanced", "music_start_age": 8
        },
        "raw_user_input": "my piano is black", "current_page": "/pianos"
    })
    for i, step in enumerate(policy.conversation):
        condition = step.if_ or step.elif_
        if condition:
            try:
                eval(condition, {}, mock_context)
            except Exception as e:
                print(f"   ⚠️  {filename} → Erreur dans la condition step[{i}]:\n      ✗ {condition}\n      → {type(e).__name__}: {e}")

# ─────────────── Validation principale ───────────────
BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATE_DIR = STATIC_DIR / "agents" / "templates"
PROMPT_DIR = STATIC_DIR / "agents" / "prompts"

def validate_prompt_exists(agent_name: str, prompt_dir: Path) -> bool:
    prompt_path = prompt_dir / f"prompt_{agent_name}.j2"
    if not prompt_path.exists():
        print(f"   ⚠️  Missing prompt: {prompt_path}")
        return False
    return True

def validate_policy_file(filepath: Path, prompt_dir: Path) -> bool:
    from app.models.policy_model import Policy  # ou autre chemin si déplacé
    ok = True
    try:
        data = yaml.safe_load(filepath.read_text(encoding="utf-8"))
        policy = Policy(**data)
        agent_name = filepath.stem

        if not validate_prompt_exists(agent_name, prompt_dir):
            ok = False

        validate_policy_variables(policy, filepath.name)
        validate_conversation_conditions(policy, filepath.name)

        # ✅ [NOUVEAU] — Validation optionnelle du bloc "start"
        start = data.get("start")
        if start:
            if "say" not in start or not isinstance(start["say"], str):
                print(f"   ❌ {filepath.name} — invalid `start.say`: must be a string")
                ok = False

            if "actions" in start and not isinstance(start["actions"], list):
                print(f"   ❌ {filepath.name} — `start.actions` must be a list")
                ok = False

            for action in start.get("actions", []):
                if not isinstance(action, dict):
                    print(f"   ❌ {filepath.name} — `start.actions` contains non-dict")
                    ok = False
                elif "trigger_event" not in action and "route_to" not in action:
                    print(f"   ❌ {filepath.name} — action in `start.actions` missing `trigger_event` or `route_to`")
                    ok = False

        print(f"   ✅ {filepath.name} is valid ✓")

    except (ValidationError, yaml.YAMLError) as e:
        print(f"   ❌ {filepath.name} invalid:\n{e}")
        ok = False

    return ok


def validate_all_policies(template_dir: Path, prompt_dir: Path) -> None:
    print(f"🔍 Validating YAML policies in: {template_dir}")
    has_error = False
    for file in sorted(template_dir.glob("*.yml")):
        print(f" ─ {file.name}")
        if not validate_policy_file(file, prompt_dir):
            has_error = True
    if has_error:
        print("❌ Validation finished with errors.")
        sys.exit(1)
    else:
        print("🎉 All policies and prompts are valid!")

# ─────────────── CLI ───────────────
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Validate all AI policy YAMLs + prompt templates")
    parser.add_argument("directory", nargs="?", default=str(TEMPLATE_DIR),
                        help="Path to policy directory (default: static/agents/templates)")
    args = parser.parse_args()

    try:
        validate_all_policies(Path(args.directory), PROMPT_DIR)
    except Exception as exc:
        print(f"🔥 Fatal error: {exc}")
        sys.exit(1)
