# ✅ app/core/settings.py
from pytune_configuration import config, SimpleConfig

config = config or SimpleConfig()

def get_llm_backend() -> str:
    return config.LLM_BACKEND


def get_openai_key() -> str:
    return config.OPEN_AI_PYTUNE_API_KEY


def get_ollama_url() -> str:
    return config.OLLAMA_URL