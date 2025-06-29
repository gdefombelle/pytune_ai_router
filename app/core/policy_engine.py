from app.models.policy_model import Policy
from pytune_data.models import UserContext
from pydantic import ValidationError
from pprint import pprint


class DotDict(dict):
    """Permet d'accéder aux clés d'un dictionnaire comme des attributs (dot notation)."""
    __getattr__ = dict.get
    __setattr__ = dict.__setitem__
    __delattr__ = dict.__delitem__


def deep_dotdict(obj):
    if isinstance(obj, dict):
        return DotDict({k: deep_dotdict(v) for k, v in obj.items()})
    elif isinstance(obj, list):
        return [deep_dotdict(v) for v in obj]
    return obj


async def evaluate_policy(policy_data: dict, user_context: UserContext) -> dict:
    """
    Évalue la politique (policy YAML) en fonction du contexte utilisateur
    et retourne la première réponse correspondant à une condition.
    """
    try:
        policy = Policy(**policy_data)
    except ValidationError as e:
        print("❌ Erreur de validation du fichier policy YAML:", e)
        raise ValueError(f"Policy YAML structure invalid: {e}")

    flat_context = flatten_user_context(user_context)
    flat_context = deep_dotdict(flat_context)
    # ✅ Appliquer les variables de policy
    variables = policy.context.get("variables", {})
    for var_name, expression in variables.items():
        try:
            flat_context[var_name] = eval(expression, {}, flat_context)
        except Exception as e:
            print(f"⚠️ Erreur d'évaluation de la variable {var_name}: {e}")

    pprint(flat_context.get("user_profile", {}))

    for step in policy.conversation:
        condition = step.if_ or step.elif_

        if condition:
            try:
                match = bool(eval(condition, {}, flat_context))
                print(f"🔎 Test de la condition '{condition}': {match}")
            except Exception as e:
                print(f"❌ Erreur dans l'évaluation de la condition '{condition}': {e}")
                match = False

            if match:
                print(f"✅ Condition matchée: {condition}")
                return format_response(step)

        elif step.else_:
            print("🛜 Aucun match avant, fallback sur else.")
            return format_response(step)

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
    """
    flat = {}

    # 1. Groupe principal : user_profile
    flat["user_profile"] = {
        "firstname": user_context.get("firstname"),
        "lastname": user_context.get("lastname"),
        "form_completed": user_context.get("form_completed"),
        "logged_in": True,
        "city": user_context.get("city"),
        "country": user_context.get("country"),
    }

    # 2. 🔁 Écrase les champs avec ceux de agent_form_snapshot (plus frais)
    snapshot = user_context.get("agent_form_snapshot") or {}
    for field, value in snapshot.items():
        flat["user_profile"][field] = value

    # 3. Groupes secondaires
    flat["user_pianos"] = {
        "count": len(user_context.get("pianos") or [])
    }

    flat["last_diagnosis"] = {
        "exists": user_context.get("last_diagnosis_exists", False)
    }

    flat["tuning_session"] = {
        "exists": user_context.get("tuning_session_exists", False)
    }

    flat["user_language"] = user_context.get("language", "en")
    flat["user_history"] = user_context.get("history", [])

    # 4. 🔁 Ajoute le reste du contexte à la racine
    for key, value in user_context.items():
        if key in flat and isinstance(flat[key], dict) and isinstance(value, dict):
            flat[key].update(value)
        elif key not in flat:
            flat[key] = value

    # 5. Définit toujours user_input
    flat["user_input"] = user_context.get("user_input", "")

    return flat


def eval_condition(condition: str, context: dict) -> bool:
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
