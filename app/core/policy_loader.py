import json
import re
import yaml
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, TemplateNotFound

from app.core.policy_engine import evaluate_policy
from app.models.policy_model import AgentResponse
from app.core.paths import PROMPT_DIR, POLICY_DIR
from pytune_llm.llm_connector import call_llm
from pytune_chat.store import get_conversation_history
from uuid import UUID

from app.utils.templates import interpolate_yaml

# 🔧 Jinja2 environment
jinja_env = Environment(loader=FileSystemLoader(PROMPT_DIR), autoescape=False)


def load_yaml(agent_name: str) -> dict:
    path = POLICY_DIR / f"{agent_name}.yml"
    if not path.exists():
        raise FileNotFoundError(f"Policy file not found at: {path}")
    with path.open("r", encoding="utf-8") as f:
        return yaml.safe_load(f)


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


async def load_policy_and_resolve(agent_name: str, user_context: dict) -> AgentResponse:
    chat_id = user_context.get("conversation_id")
    raw_input = user_context.get("raw_user_input")

    policy_data = load_yaml(agent_name)

    # ✅ [NOUVEAU] Si aucun input utilisateur et bloc start présent : on démarre par là
    already_started = user_context.get("has_started") is True
    if not raw_input and not already_started and "start" in policy_data:
        block = policy_data["start"]
        return AgentResponse(
            message=interpolate_yaml(block.get("say", ""), user_context),
            actions=block.get("actions", []),
            context_update={"has_started": True},
        )

    # 🔁 Si chat en cours + message texte, injecte l'historique
    if chat_id and raw_input:
        try:
            chat_history = await get_conversation_history(UUID(chat_id))
            if chat_history:
                user_context["chat_history"] = chat_history[-10:]
        except Exception as e:
            print("⚠️ Failed to load chat history:", e)

    # 1. Évaluation des règles conditionnelles
    evaluated_response = await evaluate_policy(policy_data, user_context)

    # 2. Appel LLM si réponse nécessite ${llm_response}
    message = evaluated_response.get("message", "")
    if "${llm_response}" in message:
        prompt = render_prompt_template(agent_name, user_context)
        llm_response = await call_llm(
            prompt=prompt,
            context=user_context,
            metadata=policy_data.get("metadata", {})
        )
        message = message.replace("${llm_response}", llm_response)

    # 3. Fallback LLM complet si aucune règle n'a matché
    if not message.strip():
        try:
            prompt = render_prompt_template(agent_name, user_context)
            message = await call_llm(
                prompt=prompt,
                context=user_context,
                metadata=policy_data.get("metadata", {})
            )
        except FileNotFoundError:
            message = "🤖 I’m here, but no rule matched and no prompt was found."

    # 4. Extraction éventuelle de JSON structuré
    context_update = {}
    try:
        match = re.search(r"```json\s*({[\s\S]+?})\s*```", message)
        if match:
            context_update = json.loads(match.group(1))
            message = message.split("```")[0].strip()
    except Exception as e:
        print("[⚠️ JSON extraction failed]", str(e))

    return AgentResponse(
        message=message.strip(),
        actions=evaluated_response.get("actions", []),
        meta=evaluated_response.get("meta", {}),
        context_update=context_update or None
    )
