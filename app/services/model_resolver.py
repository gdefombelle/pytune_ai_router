import json
import re
from typing import Dict, Optional

from pytune_llm.llm_connector import call_llm
from pytune_llm.task_reporting.reporter import TaskReporter
from app.core.prompt_builder import render_prompt_template
from pytune_data.piano_data_service import search_model_full, get_manufacturer_name


async def resolve_model_name(
        model_name: str, 
        first_piano: dict, 
        manufacturer_id: int,
        reporter: Optional[TaskReporter]) -> Dict:
    """
    Résolution du nom de modèle de piano :
    1. Recherche dans la base PyTune
    2. Sinon, enrichissement structuré via GPT-5xx avec prompt Jinja centralisé
    """

    # 🔍 Étape 1 — recherche dans la base
    result = await search_model_full(model_name, manufacturer_id, email=None)
    print("🔍 Résultat brut de search_model_full:", result)

    if result:
        top = result[0]
        CATEGORY_MAP = {1: "grand", 2: "upright", "1": "grand", "2": "upright"}
        if "kind" in top:
            top["kind"] = CATEGORY_MAP.get(top["kind"], top["kind"])
        return {
            "status": "found",
            "source": "database",
            **top
        }

    # 🧠 Étape 2 — enrichissement LLM via prompt Jinja
    try:
        # 🏷️ Nom humain du fabricant (Pleyel, Yamaha, etc.)
        brand_name = await get_manufacturer_name(manufacturer_id)

        prompt = render_prompt_template(
            agent_name="model_enrichment",
            context={
                "model_name": model_name,
                "brand_name": brand_name,
                "category": first_piano.get("category"),
                "type": first_piano.get("type"),
                "size_cm": first_piano.get("size_cm"),
                "year_estimated": first_piano.get("year_estimated")
            }
        )


        llm_output = await call_llm(
            prompt=prompt,
            context={"source": "model_resolver", "attempted": model_name},
            metadata={"llm_backend": "openai"},
            reporter=reporter
        )

        match = re.search(r"{[\s\S]+?}\s*", llm_output)
        raw_json = match.group(0).strip() if match else llm_output.strip()
        parsed = json.loads(raw_json)

        if parsed.get("status") == "not_found":
            return {
                "status": "rejected",
                "source": "llm",
                "attempted": model_name,
                "reason": parsed.get("notes", "Unknown model"),
                "llm_data": parsed  # ✅ ceci manquait !
            }


        return {
            "status": parsed["status"],
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
            "attempted": model_name,
            "error": str(e)
        }
