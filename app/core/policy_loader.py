import json
import re
import yaml
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, TemplateNotFound

from app.core.policy_engine import evaluate_policy
from app.models.policy_model import AgentResponse
from app.core.paths import PROMPT_DIR, POLICY_DIR
from pytune_llm.llm_connector import call_llm

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
        return template.render(context)
    except TemplateNotFound:
        raise FileNotFoundError(f"Prompt template not found for agent '{agent_name}' at {PROMPT_DIR}/{template_file}")
    except Exception as e:
        print(f"⚠️ Jinja2 rendering error for '{agent_name}':", str(e))
        raise


async def load_policy_and_resolve(agent_name: str, user_context: dict) -> AgentResponse:
    policy_data = load_yaml(agent_name)

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

    # 3. Si pas de message (et aucune règle ne match), fallback LLM complet
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

    # 4. Extraction éventuelle de JSON structuré depuis message
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
