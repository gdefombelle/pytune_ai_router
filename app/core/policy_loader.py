# ✅ app/core/policy_loader.py

import os
from pathlib import Path
import yaml
from string import Template
from app.core.policy_engine import evaluate_policy
from app.models.policy_model import AgentResponse
from app.core.llm_connector import call_llm

# 🔧 Définir la racine du projet
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_yaml(path: str | Path) -> dict:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Policy file not found at: {path}")
    with path.open("r", encoding="utf-8") as file:
        return yaml.safe_load(file)


async def load_policy_and_resolve(agent_name: str, user_context: dict) -> AgentResponse:
    """
    Charge et exécute une policy YAML en fonction du contexte utilisateur.
    """
    # 1. Chemin du fichier de policy
    policy_path = os.path.join(BASE_DIR, "static", "agents", "templates", f"{agent_name}.yml")
    policy_data = load_yaml(policy_path)

    # 2. Évaluation principale des règles (if/else/say)
    evaluated_response = await evaluate_policy(policy_data, user_context)

    # 3. Si "say" est présent → interpolation + renvoi direct
    if "say" in evaluated_response:
        evaluated_response["message"] = evaluated_response.pop("say")

        # 🔁 Interpolation template
        if "message" in evaluated_response:
            template = Template(evaluated_response["message"])
            evaluated_response["message"] = template.safe_substitute(user_context)

    # 4. Sinon → fallback IA via prompt_template (si défini)
    elif "prompt_template" in policy_data:
        prompt_template = policy_data["prompt_template"]
        prompt = Template(prompt_template).safe_substitute(user_context)
        message = await call_llm(prompt=prompt, context=user_context)
        evaluated_response["message"] = message

    # 5. Dernier recours : pas de réponse possible
    else:
        evaluated_response["message"] = "🤖 I’m here, but no rule matched and no AI fallback was defined."

    # 6. Emballage dans un AgentResponse
    return AgentResponse(
        message=evaluated_response.get("message", "No message"),
        actions=evaluated_response.get("actions", []),
        meta=evaluated_response.get("meta", {})
    )
