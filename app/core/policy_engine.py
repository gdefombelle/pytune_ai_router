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

def flatten_user_context(user_context: UserContext) -> dict:
    return {
        "user_profile": DotDict({
            "firstname": user_context.firstname,
            "form_completed": user_context.form_completed,
        }),
        "user_pianos": DotDict({
            "count": len(user_context.pianos),
        }),
        "last_diagnosis": DotDict({
            "exists": user_context.last_diagnosis_exists,
        }),
        "tuning_session": DotDict({
            "exists": user_context.tuning_session_exists,
        }),
        "user_language": user_context.language,
    }

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
