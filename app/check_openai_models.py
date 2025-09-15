import openai
import os
from pytune_configuration.sync_config_singleton import config, SimpleConfig

config = config or SimpleConfig()

# Charge ta clé API OpenAI depuis une variable d'environnement
openai.api_key = config.OPEN_AI_PYTUNE_API_KEY

def list_models():
    try:
        models = openai.models.list()
        print("✅ Available models:")
        for model in models.data:
            print(f"- {model.id}")
    except Exception as e:
        print(f"❌ Failed to fetch models: {e}")

if __name__ == "__main__":
    list_models()
