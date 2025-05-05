# app/core/llm_client.py
import os
import json
import openai
from pytune_configuration.sync_config_singleton import config, SimpleConfig


config = config or SimpleConfig()
openai.api_key = config.OPEN_AI_PYTUNE_API_KEY 

async def ask_llm(prompt_template: str, user_input: str, context: dict) -> str:
    """
    Envoie une requête au LLM avec un prompt enrichi du contexte utilisateur.
    Le prompt_template provient de la policy YAML (ex: policy.prompt_template).
    """
    # Interpolation du prompt
    from string import Template
    full_prompt = Template(prompt_template).safe_substitute(
        user_input=user_input,
        **context
    )

    # Appel à OpenAI (ou autre backend LLM)
    response = await openai.ChatCompletion.acreate(
        model="gpt-4",
        messages=[
            {"role": "system", "content": "You are PyTune AI assistant."},
            {"role": "user", "content": full_prompt}
        ]
    )
    return response.choices[0].message.content
