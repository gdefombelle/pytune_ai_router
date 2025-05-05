from app.models.policy_model import Policy
from pytune_data.models import UserContext
from pydantic import ValidationError

class DotDict(dict):
    """
    Permet d'accéder aux clés d'un dictionnaire comme des attributs (dot notation).
    """
    __getattr__ = dict.get
    __setattr__ = dict.__setitem__
    __delattr__ = dict.__delitem__

async def evaluate_policy(policy_data: dict, user_context: UserContext) -> dict:
    """
    Évalue la politique (policy YAML) en fonction du contexte utilisateur
    et retourne la première réponse correspondant à une condition.
    """
    try:
        # 🔥 Charge le YAML dans un objet Pydantic (facultatif mais recommandé)
        policy = Policy(**policy_data)
    except ValidationError as e:
        print("❌ Erreur de validation du fichier policy YAML:", e)
        raise ValueError(f"Policy YAML structure invalid: {e}")

    # 🔥 Transforme le UserContext en flat_context structuré pour eval()
    flat_context = flatten_user_context(user_context)

    # 🔥 DEBUG : Montre le contexte
    print("🔎 Flat user context:", flat_context)

    for step in policy.conversation:
        condition = step.if_ or step.elif_

        if condition:
            try:
                match = eval(condition, {}, flat_context)
                print(f"🔎 Test de la condition '{condition}': {match}")
            except Exception as e:
                print(f"❌ Erreur dans l'évaluation de la condition '{condition}': {e}")
                match = False

            if match:
                print(f"✅ Condition matchée: {condition}")
                return format_response(step)

        elif step.else_:
            print(f"🛜 Aucun match avant, fallback sur else.")
            return format_response(step)

    # 🔥 Aucun match trouvé (vraiment dernier recours)
    print("⚠️ Aucune condition correspondante trouvée dans la policy.")
    return {
        "message": "No matching step found.",
        "actions": [],
        "meta": {}
    }

def flatten_user_context(user_context: dict) -> dict:
    """
    À partir d’un contexte utilisateur riche (dict), produit une version “flat”
    directement utilisable dans eval(condition).
    Supporte les structures en pointillés : user_profile.x, user_pianos.count, etc.
    """
    flat = {}

    # 1. Rattacher les groupes connus
    flat["user_profile"] = {
        "firstname": user_context.get("firstname"),
        "lastname": user_context.get("lastname"),
        "form_completed": user_context.get("form_completed"),
        "logged_in": True,
        "city": user_context.get("city"),
        "country": user_context.get("country"),
    }

    flat["user_pianos"] = {
        "count": len(user_context.get("pianos") or []),
    }

    flat["last_diagnosis"] = {
        "exists": user_context.get("last_diagnosis_exists", False)
    }

    flat["tuning_session"] = {
        "exists": user_context.get("tuning_session_exists", False)
    }

    flat["user_language"] = user_context.get("language", "en")
    flat["user_history"] = user_context.get("history", [])

    return flat

def eval_condition(condition: str, context: dict) -> bool:
    """
    Évalue dynamiquement une condition sur le contexte utilisateur.
    """
    try:
        return eval(condition, {}, context)
    except Exception as e:
        print(f"⚠️ Failed to evaluate condition '{condition}': {e}")
        return False

def format_response(step) -> dict:
    return {
        "message": step.say,
        "actions": [action.model_dump() for action in step.actions] if step.actions else [],
        "meta": {},
    }
