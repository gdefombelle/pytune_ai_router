# routes/chat.py
from fastapi import APIRouter
from core.policy_loader import load_policy
from core.prompt_builder import build_prompt_from_policy

router = APIRouter()

@router.post("/chat")
async def chat_handler():
    # Exemple de contexte utilisateur simulé
    user_context = {
        "user_profile": {
            "form_completed": False,
            "firstname": "Gabriel"
        },
        "user_pianos": [],
        "user_has_diagnosis": False,
    }

    # Flatten le contexte pour eval (tu peux faire mieux si besoin)
    flat_ctx = {
        "user_profile": user_context["user_profile"],
        "user_profile.firstname": user_context["user_profile"]["firstname"],
        "user_profile.form_completed": user_context["user_profile"]["form_completed"],
        "user_has_diagnosis": user_context["user_has_diagnosis"]
    }

    steps = load_policy("policies/agent_policy.yml")
    prompt = build_prompt_from_policy(steps, flat_ctx)

    return {
        "prompt": prompt
    }
