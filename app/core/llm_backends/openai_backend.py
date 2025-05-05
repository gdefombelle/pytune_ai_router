# app/core/llm_backends/openai_backend.py

import httpx
from app.core.settings import get_openai_key


async def call_openai_llm(prompt: str, context: dict) -> str:
    api_key = get_openai_key()

    payload = {
        "model": "gpt-3.5-turbo",
        "messages": [
            {
                "role": "system",
                "content": "You are a helpful assistant for PyTune users. Be concise, friendly, and proactive."
            },
            {
                "role": "user",
                "content": prompt
            }
        ],
        "temperature": 0.7,
        "max_tokens": 500,
    }

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(
            "https://api.openai.com/v1/chat/completions",
            headers=headers,
            json=payload
        )

        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"].strip()
