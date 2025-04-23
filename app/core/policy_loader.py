# app/core/policy_loader.py

import os
import yaml
from app.core.policy_engine import evaluate_policy
from app.models.policy_model import AgentResponse
from pytune_data.models import UserContext
from string import Template

# Définir la racine du projet
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # <- un cran au-dessus de /core

def load_yaml(path: str) -> dict:
    """
    Charge un fichier YAML et retourne son contenu en dictionnaire.
    """
    with open(path, "r", encoding="utf-8") as file:
        return yaml.safe_load(file)

async def load_policy_and_resolve(agent_name: str, user_context: UserContext) -> AgentResponse:
    """
    Load a policy YAML file and resolve the conversation flow based on the user context.
    """
    # 🔥 1. Construire le chemin correct vers static/agents/
    policy_path = os.path.join(BASE_DIR, "static", "agents", f"{agent_name}.yml")
    policy_path = os.path.abspath(policy_path)

    # 🔥 2. Charger la policy YAML
    policy_data = load_yaml(policy_path)

    # 🔥 3. Lancer l'évaluation de la policy avec le contexte utilisateur
    evaluated_response = await evaluate_policy(policy_data, user_context)

    # 🔁 Si le champ 'say' est présent, transforme-le en 'message'
    if "say" in evaluated_response:
        evaluated_response["message"] = evaluated_response.pop("say")

    # 🔡 Interpolation via Template
    if "message" in evaluated_response:
        template = Template(evaluated_response["message"])
        evaluated_response["message"] = template.safe_substitute({
            "firstname": user_context.firstname
        })

    # 🔥 4. Retourner un AgentResponse formaté
    return AgentResponse(
        message=evaluated_response.get("message", "No message"),
        actions=evaluated_response.get("actions", []),
        meta=evaluated_response.get("meta", {})
    )
