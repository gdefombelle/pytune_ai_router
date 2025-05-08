import httpx
from app.core.settings import get_openai_key


async def call_openai_llm(prompt: str, context: dict) -> str:
    api_key = get_openai_key()
    model = context.get("llm_model", "gpt-3.5-turbo")  # ✅ utilise le modèle précisé dans la policy ou fallback

    payload = {
        "model": model,
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
