# ✅ app/core/llm_engine.py
from app.core.settings import get_llm_backend, get_openai_key
import httpx
from string import Template

async def call_llm(user_input: str, context: dict, prompt_template: str) -> str:
    backend = get_llm_backend()

    if backend == "openai":
        return await call_openai_llm(user_input, context, prompt_template)

    raise ValueError(f"Unsupported LLM backend: {backend}")

def interpolate_template(template: str, user_input: str, context: dict) -> str:
    return Template(template).safe_substitute({"user_input": user_input, **context})


async def call_openai_llm(user_input: str, context: dict, prompt_template: str) -> str:
    interpolated_prompt = interpolate_template(prompt_template, user_input, context)
    headers = {
        "Authorization": f"Bearer {get_openai_key()}",
        "Content-Type": "application/json"
    }

    payload = {
        "model": "gpt-4",  # or "gpt-3.5-turbo"
        "messages": [
            {"role": "system", "content": "You are a helpful assistant."},
            {"role": "user", "content": interpolated_prompt}
        ],
        "temperature": 0.7
    }

    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.post("https://api.openai.com/v1/chat/completions", json=payload, headers=headers)
        response.raise_for_status()
        data = response.json()
        return data["choices"][0]["message"]["content"].strip()
