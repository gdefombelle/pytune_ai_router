import httpx
from app.core.settings import get_ollama_url, config

async def call_ollama_llm(prompt: str, context: dict) -> str:
    ollama_url = get_ollama_url()
    model_name = context.get("llm_model") or config.OLLAMA_MODEL or "mistral"

    payload = {
        "model": model_name,
        "prompt": prompt,
        "stream": False,
    }

    try:
        async with httpx.AsyncClient(timeout=40.0) as client:
            response = await client.post(f"{ollama_url}/api/generate", json=payload)
            response.raise_for_status()
            result = response.json()
            return result.get("response", "").strip()

    except Exception as e:
        raise RuntimeError(f"❌ Failed to call Ollama model '{model_name}': {e}")
