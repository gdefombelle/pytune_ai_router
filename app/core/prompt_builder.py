# 👈 ← Construit le prompt à partir de la policy
from typing import Optional
from pytune_data.models import UserContext


def build_prompt(user_context: UserContext, page: str, user_message: Optional[str] = None) -> str:
    """
    Construit un prompt pour l'agent AI en fonction du contexte utilisateur et de la page actuelle.
    """
    prompt = []

    # 🎯 Page actuelle
    prompt.append(f"Current page: {page}")

    # 📋 Contexte utilisateur
    prompt.append("User Context:")
    prompt.append(f"- Firstname: {user_context.firstname}")
    prompt.append(f"- Profile completed: {user_context.form_completed}")
    prompt.append(f"- Number of pianos: {len(user_context.pianos)}")
    prompt.append(f"- Diagnosis exists: {user_context.last_diagnosis_exists}")
    prompt.append(f"- Tuning session exists: {user_context.tuning_session_exists}")
    prompt.append(f"- Language: {user_context.language}")

    # 🧠 Message de l'utilisateur s'il existe
    if user_message:
        prompt.append("User just asked:")
        prompt.append(f'"{user_message}"')

    # 🎤 Instructions à l'IA
    prompt.append("""
    Your goal is to guide the user in a helpful, friendly and clear way.
    If they seem lost or hesitant, reassure them.
    If they mention 'tuning', but the profile isn't completed yet,
    explain why it's important to complete it first.
    If the user is on the profile page, explain each field if needed.
    """)

    return "\n".join(prompt)
