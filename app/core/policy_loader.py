import os
import json
import re
import yaml
from pathlib import Path
from string import Template

from app.core.policy_engine import evaluate_policy
from app.models.policy_model import AgentResponse
from app.core.llm_connector import call_llm
from app.services.brand_resolver import resolve_brand_name

# 🔧 Racine du projet
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_yaml(path: str | Path) -> dict:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Policy file not found at: {path}")
    with path.open("r", encoding="utf-8") as file:
        return yaml.safe_load(file)


def interpolate_template(template_str: str, context: dict) -> str:
    try:
        return Template(template_str).safe_substitute(flatten_for_template(context))
    except Exception as e:
        print(f"⚠️ Erreur interpolation : {e}")
        return template_str


def flatten_for_template(data: dict, parent_key='', sep='.') -> dict:
    items = {}
    for k, v in data.items():
        new_key = f"{parent_key}{sep}{k}" if parent_key else k
        if isinstance(v, dict):
            items.update(flatten_for_template(v, new_key, sep=sep))
        else:
            items[new_key] = v
    return items


async def load_policy_and_resolve(agent_name: str, user_context: dict) -> AgentResponse:
    # 1. Charger le fichier YAML
    policy_path = os.path.join(BASE_DIR, "static", "agents", "templates", f"{agent_name}.yml")
    policy_data = load_yaml(policy_path)

    # 2. Évaluer les règles YAML (if / elif / else)
    evaluated_response = await evaluate_policy(policy_data, user_context)

    # 3. Résolution via LLM si demandé
    if "message" in evaluated_response:
        raw_message = evaluated_response["message"]

        if "${llm_response}" in raw_message and "prompt_template" in policy_data:
            prompt = interpolate_template(policy_data["prompt_template"], user_context)
            llm_response = await call_llm(prompt=prompt, context=user_context, metadata=policy_data.get("metadata", {}))
            raw_message = raw_message.replace("${llm_response}", llm_response)

        evaluated_response["message"] = interpolate_template(raw_message, user_context)

    elif "prompt_template" in policy_data:
        prompt = interpolate_template(policy_data["prompt_template"], user_context)
        evaluated_response["message"] = await call_llm(prompt=prompt, context=user_context, metadata=policy_data.get("metadata", {}))

    else:
        evaluated_response["message"] = "🤖 I’m here, but no rule matched and no AI fallback was defined."

    # 4. Extraction éventuelle d’un bloc JSON structuré
    context_update = {}

    try:
        match = re.search(r"```json\s*({[\s\S]+})\s*```", evaluated_response["message"])
        if match:
            context_update = json.loads(match.group(1))
            evaluated_response["message"] = evaluated_response["message"].split("```")[0].strip()
    except Exception as e:
        print("[⚠️ JSON extraction failed]", str(e))

    # 5. 🔍 Vérification intelligente de la marque si first_piano.brand présent
    first_piano = context_update.get("first_piano", {})
    brand = first_piano.get("brand")

    if brand:
        email = user_context.get("email", "")
        result = await resolve_brand_name(brand, email)
        context_update["brand_resolution"] = result

        corrected = (
            result.get("matched_name") or
            result.get("corrected") or
            result.get("llm_data", {}).get("brand")
        )
        
        # ✅ 5.a Cas : rejeté → on override le message directement
        if result["status"] == "rejected":
            evaluated_response["message"] = (
                f"⚠️ The brand **{brand}** doesn’t appear to be a known piano manufacturer.\n"
                f"If you're unsure, please upload a photo of the piano’s logo or fallboard."
            )
            evaluated_response["actions"] = [
                {
                    "label": "📸 Upload a photo",
                    "type": "upload",
                    "target": "photo_upload"
                }
            ]
             # 🧹 Supprimer la marque du contexte pour éviter l’affichage dans le tableau
            context_update["first_piano"]["brand"] = ""

        # ✅ 5.b Cas : correction → injecte suggestion
        elif corrected and corrected != brand:
            context_update["first_piano"]["brand"] = corrected
            confirmation_msg = (
                f"\n\n🔎 Did you mean **{corrected}** instead of **{brand}**? "
                "If you're unsure, feel free to upload a photo of your piano's logo or fallboard."
            )
            evaluated_response["message"] += confirmation_msg

    # 6. Retour
    return AgentResponse(
        message=evaluated_response.get("message", "No message"),
        actions=evaluated_response.get("actions", []),
        meta=evaluated_response.get("meta", {}),
        context_update=context_update or None
    )
