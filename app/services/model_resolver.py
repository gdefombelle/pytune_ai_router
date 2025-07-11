import json
import re
from typing import Dict
from pytune_llm.llm_connector import call_llm
from pytune_data.piano_data_service import search_model_full

async def resolve_model_name(model_name: str, manufacturer_id: int) -> Dict:
    """
    Résolution du nom de modèle de piano.
    1. Recherche dans la base PyTune
    2. Si introuvable, enrichissement via LLM
    """

    # ✅ Étape 1 : recherche dans la base
    result = await search_model_full(model_name, manufacturer_id, email=None)
    print("🔍 Résultat brut de search_model_full:", result)

    if result:
        top = result[0]
        return {
            "status": "found",
            "source": "database",
            **top  # ⬅️ merge tout le contenu de top directement ici
        }

    # 🔍 Étape 2 : enrichissement LLM
    enrichment_prompt = f"""
The user entered a piano model name: "{model_name}".

Determine whether this model is known and extract its category, type, and size if possible.

Return a valid JSON object like:
{{
  "model": "C7",
  "category": "grand",
  "type": "concert grand",
  "size_cm": 227,
  "notes": "Used in Yamaha professional series"
}}

If unknown, return:
{{ "error": "Unknown model" }}
"""

    try:
        llm_output = await call_llm(
            prompt=enrichment_prompt,
            context={"source": "model_resolver", "attempted": model_name},
            metadata={"llm_backend": "openai", "llm_model": "gpt-3.5-turbo"}
        )

        match = re.search(r"{[\s\S]+}", llm_output)
        raw_json = match.group(0) if match else llm_output.strip()
        parsed = json.loads(raw_json)

        if "error" in parsed:
            return {
                "status": "rejected",
                "source": "llm",
                "attempted": model_name,
                "reason": parsed["error"]
            }

        return {
            "status": "enriched",
            "source": "llm",
            "original": model_name,
            "corrected": parsed.get("model", model_name),
            "llm_data": parsed
        }

    except Exception as e:
        print("⚠️ LLM enrichment failed:", repr(e))
        return {
            "status": "llm_error",
            "source": "llm_error",
            "attempted": model_name
        }
