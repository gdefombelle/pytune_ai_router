# 👈 ← Construit le prompt à partir de la policy
from pathlib import Path
from typing import Optional

from jinja2 import Environment, FileSystemLoader, TemplateNotFound
from pytune_data.models import UserContext
from app.core.paths import PROMPT_DIR, POLICY_DIR

# 🔧 Jinja2 environment
jinja_env = Environment(loader=FileSystemLoader(PROMPT_DIR), autoescape=False)

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

def render_prompt_template(agent_name: str, context: dict) -> str:
    template_file = f"prompt_{agent_name}.j2"
    try:
        template = jinja_env.get_template(template_file)
        print("📦 Jinja context keys:", context.keys())
        print("🧪 last_prompt =", context.get("last_prompt"))
        return template.render(context)
    except TemplateNotFound:
        raise FileNotFoundError(f"Prompt template not found for agent '{agent_name}' at {PROMPT_DIR}/{template_file}")
    except Exception as e:
        print(f"⚠️ Jinja2 rendering error for '{agent_name}':", str(e))
        raise

def load_prompt_template_source(template_name: str) -> str:
    """
    Charge le contenu brut d’un template Jinja (.j2) depuis PROMPT_DIR.

    Ex:
        load_prompt_template_source("prompt_piano_agent_conversation.j2")
    """
    path = Path(PROMPT_DIR) / template_name

    if not path.exists():
        raise FileNotFoundError(f"Prompt template not found: {path}")

    return path.read_text(encoding="utf-8")