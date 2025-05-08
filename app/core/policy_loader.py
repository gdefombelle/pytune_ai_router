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


def interpolate_template(template_str: str, context: dict) -> str:
    """
    Remplace les variables du template (ex: ${firstname}, ${user_profile.firstname})
    à partir d’un dictionnaire de contexte.
    """
    try:
        return Template(template_str).safe_substitute(flatten_for_template(context))
    except Exception as e:
        print(f"⚠️ Erreur lors de l'interpolation du template : {e}")
        return template_str


def flatten_for_template(data: dict, parent_key='', sep='.') -> dict:
    """
    Aplatis un dictionnaire imbriqué pour permettre ${user_profile.firstname} dans les templates.
    """
    items = {}
    for k, v in data.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.update(flatten_for_template(v, new_key, sep=sep))
        else:
            items[new_key] = v
    return items


async def load_policy_and_resolve(agent_name: str, user_context: dict) -> AgentResponse:
    """
    Charge et exécute une policy YAML en fonction du contexte utilisateur.
    """
    # 1. Chemin du fichier de policy
    policy_path = os.path.join(BASE_DIR, "static", "agents", "templates", f"{agent_name}.yml")
    policy_data = load_yaml(policy_path)

    # 2. Évaluation principale des règles (if/elif/else)
    evaluated_response = await evaluate_policy(policy_data, user_context)

    # 3. Si "message" contient ${llm_response}, on appelle le LLM
    if "message" in evaluated_response:
        raw_message = evaluated_response["message"]
        if "${llm_response}" in raw_message and "prompt_template" in policy_data:
            prompt = interpolate_template(policy_data["prompt_template"], user_context)
            llm_response = await call_llm(prompt=prompt, context=user_context, metadata=policy_data.get("metadata", {}))
            raw_message = raw_message.replace("${llm_response}", llm_response)
        evaluated_response["message"] = interpolate_template(raw_message, user_context)

    # 4. Sinon → fallback IA via prompt_template
    elif "prompt_template" in policy_data:
        prompt = interpolate_template(policy_data["prompt_template"], user_context)
        message = await call_llm(prompt=prompt, context=user_context)
        evaluated_response["message"] = message

    # 5. Dernier recours : pas de message possible
    else:
        evaluated_response["message"] = "🤖 I’m here, but no rule matched and no AI fallback was defined."

    # 6. Emballage dans un AgentResponse
    return AgentResponse(
        message=evaluated_response.get("message", "No message"),
        actions=evaluated_response.get("actions", []),
        meta=evaluated_response.get("meta", {})
    )
