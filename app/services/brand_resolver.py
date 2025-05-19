import json
import re
from app.core.llm_connector import call_llm
from pytune_data.piano_data_service import search_manufacturer


async def resolve_brand_name(brand: str, email: str) -> dict:
    """
    Résout une marque de piano :
    1. Vérifie dans la base PyTune
    2. Si introuvable, tente un enrichissement via LLM
    3. Si échec, tente une correction orthographique simple
    """

    # Étape 1 — Recherche directe dans la base PyTune
    result = await search_manufacturer(brand, email)
    if result:
        return {
            "status": "found",
            "matched_name": result[0]["name"],
            "manufacturer_id": result[0]["id"]
        }

    # Étape 2 — Enrichissement LLM avancé
    enrichment_prompt = f"""
You are an expert in historical piano manufacturers.

Given the brand name "{brand}", research and extract structured information as follows.

Please return a valid JSON object with these fields:

- "brand": Full and correct brand name (e.g. "Blüthner")
- "country": Country of origin (e.g. "Germany")
- "city": City of founding or headquarters (e.g. "Leipzig")
- "years_active": Period of activity (e.g. "1853–present")
- "acquired_by": If acquired, specify the company; otherwise, null
- "notes": A detailed paragraph including:
    - the historical context of the brand (founder, founding date, etc.)
    - technical innovations or distinctive features
    - historical events (e.g. wars, crises)
    - famous musicians or composers associated with the brand (e.g. Brahms, Debussy)

💡 Use reliable, verifiable knowledge only.
❗️Output only a valid JSON object. No explanation or preamble.

Example:

```json
{{
  "brand": "Blüthner",
  "country": "Germany",
  "city": "Leipzig",
  "years_active": "1853–present",
  "acquired_by": null,
  "notes": "Founded by Julius Blüthner in 1853 in Leipzig. Known for its Aliquot stringing system. Played by Brahms, Debussy, and Rachmaninoff."
}}
"""

    try:
        response = await call_llm(
            prompt=enrichment_prompt,
            context={"source": "brand_resolver", "attempted": brand},
            metadata={"llm_backend": "openai", "llm_model": "gpt-3.5-turbo"}
        )

        # 🧠 Extraction JSON robuste
        match = re.search(r"```json\s*({[\s\S]+?})\s*```", response)
        raw_json = match.group(1) if match else response.strip()
        parsed = json.loads(raw_json)

        return {
            "status": "enriched",
            "original": brand,
            "corrected": parsed["brand"],
            "llm_data": parsed
        }

    except Exception as e:
        print("⚠️ LLM enrichment failed:", repr(e))
        if "ReadTimeout" in str(e) or "timed out" in str(e).lower():
            return {
                "status": "llm_timeout",
                "attempted_brand": brand
            }

    # Étape 3 — Correction orthographique simple (fallback)
    correction_prompt = f"""
The user entered this brand name: "{brand}".
Try to guess the most likely correct piano manufacturer name.
Return only the corrected name in plain text.
"""

    try:
        corrected = await call_llm(
            prompt=correction_prompt,
            context={"source": "brand_resolver", "brand": brand},
            metadata={"llm_backend": "openai", "llm_model": "gpt-3.5-turbo"}
        )

        corrected = corrected.strip().splitlines()[0]
        retry = await search_manufacturer(corrected, email)

        if retry:
            return {
                "status": "corrected",
                "original": brand,
                "corrected": corrected,
                "matched_name": retry[0]["name"],
                "manufacturer_id": retry[0]["id"]
            }

    except Exception as e:
        print("⚠️ LLM correction failed:", e)

    # Échec complet
    return {
        "status": "not_found",
        "attempted_brand": brand
    }
