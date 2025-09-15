# ✅ app/core/settings.py
from pytune_configuration import config, SimpleConfig
from dotenv import load_dotenv
import os
import json

load_dotenv()  

config = config or SimpleConfig()

def get_llm_backend() -> str:
    return config.LLM_BACKEND


def get_openai_key() -> str:
    return config.OPEN_AI_PYTUNE_API_KEY


def get_ollama_url() -> str:
    return config.OLLAMA_URL

def get_supported_llm_models() -> dict:
    try:
        raw = os.getenv("SUPPORTED_LLM_MODELS", '{}')
        parsed = json.loads(raw)
        return {k: set(v) for k, v in parsed.items()}
    except Exception as e:
        print(f"⚠️ Error parsing SUPPORTED_LLM_MODELS: {e}")
        return {}
