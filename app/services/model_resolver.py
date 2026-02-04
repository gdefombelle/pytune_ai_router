import json
import re
from typing import Dict, Optional

from pytune_llm.llm_connector import call_llm
from pytune_llm.task_reporting.reporter import TaskReporter
from unidecode import unidecode
from app.core.prompt_builder import render_prompt_template

from pytune_data.piano_data_service import (
    search_model_full,
    get_manufacturer_name,
)

from pytune_data.piano_model_data_service import (
    create_piano_model_from_llm,
    normalize_label,
    normalize_piano_model_name,
)


CATEGORY_MAP = {
    1: "grand",
    2: "upright",
    "1": "grand",
    "2": "upright",
}


async def resolve_model_name(
    model_name: str,
    first_piano: dict,
    manufacturer_id: int,
    lang: Optional[str] = None,
    reporter: Optional[TaskReporter] = None,
) -> Dict:
    """
    Resolve a piano model name.

    Strategy:
    1. Look up in database (authoritative)
    2. Enrich via LLM → create model → re-query database
    3. Return DB-shaped payload ONLY
    """
    lang = lang or "en"

    # ─────────────────────────────────────────────
    # 1️⃣ Direct DB lookup
    # ─────────────────────────────────────────────
    normalized = normalize_piano_model_name(model_name)
    result = await search_model_full(normalized, manufacturer_id, email=None)

    if result:
        reporter and reporter.step(f"🎹 Model {model_name} identified") # type: ignore
        top = result[0]
        if "kind" in top:
            top["kind"] = CATEGORY_MAP.get(top["kind"], top["kind"])
        return {
            "status": "found",
            "source": "database",
            "canonical_name": top.get("name"),  
            **top,
        }

    # ─────────────────────────────────────────────
    # 2️⃣ LLM enrichment
    # ─────────────────────────────────────────────
    try:
        brand_name = await get_manufacturer_name(manufacturer_id)

        prompt = render_prompt_template(
            agent_name="model_enrichment",
            context={
                "model_name": model_name,
                "brand_name": brand_name,
                "category": first_piano.get("category"),
                "type": first_piano.get("type"),
                "size_cm": first_piano.get("size_cm"),
                "year_estimated": first_piano.get("year_estimated"),
                "user_lang": lang,
            },
        )

        llm_output = await call_llm(
            prompt=prompt,
            context={
                "source": "model_resolver",
                "attempted": model_name,
            },
            metadata={
                "llm_backend": "openai",
                "llm_model": "gpt-5.2",
            },
            reporter=reporter,
        )

        # ─────────────────────────────────────────
        # Strict JSON extraction
        # ─────────────────────────────────────────
        match = re.search(r"{[\s\S]+?}\s*", llm_output)
        raw_json = match.group(0).strip() if match else llm_output.strip()
        parsed = json.loads(raw_json)

        if parsed.get("status") != "found":
            return {
                "status": "rejected",
                "source": "llm",
                "attempted": model_name,
                "reason": parsed.get("notes", "Unknown model"),
                "llm_data": parsed,
            }

        resolved_model_name = parsed.get("model") or model_name

        # ─────────────────────────────────────────
        # 3️⃣ Create model in DB
        # ─────────────────────────────────────────
        await create_piano_model_from_llm(
            manufacturer_id=manufacturer_id,
            model_name=resolved_model_name,
            kind_label=parsed.get("category"),
            size_cm=parsed.get("size_cm"),
            piano_type_label=parsed.get("type"),
            notes=parsed.get("notes"),
            originated_by="llm",
        )

        # ─────────────────────────────────────────
        # 4️⃣ Re-query DB (SINGLE SOURCE OF TRUTH)
        # ─────────────────────────────────────────
        refreshed = await search_model_full(
            resolved_model_name,
            manufacturer_id,
            email=None,
        )

        if not refreshed:
            raise RuntimeError("Model created but not retrievable from database")

        top = refreshed[0]
        if "kind" in top:
            top["kind"] = CATEGORY_MAP.get(top["kind"], top["kind"])
        reporter and reporter.step(f"🎹 Model {model_name} identified") # type: ignore
        return {
            "status": "found",
            "source": "database",
            **top,
        }

    except Exception as e:
        print("⚠️ Model resolver failed:", repr(e))
        return {
            "status": "llm_error",
            "source": "llm_error",
            "attempted": model_name,
            "error": str(e),
        }