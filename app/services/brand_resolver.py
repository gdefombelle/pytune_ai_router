import json
import re
from app.core.llm_connector import call_llm
from pytune_data.piano_data_service import search_manufacturer


async def resolve_brand_name(brand: str, email: str) -> dict:
    """
    Résout une marque de piano :
    1. Vérifie dans la base PyTune
    2. Si introuvable, tente un enrichissement structuré via LLM
    3. Si échec, tente une correction orthographique simple
    """

    # Étape 1 — Recherche directe dans la base PyTune
    result = await search_manufacturer(brand, email)
    print("🔍 Résultat brut de search_manufacturer:", result)
    if result:
        return {
            "status": "found",
            "matched_name": result[0]["company"],
            "manufacturer_id": result[0]["id"]
        }



    # Étape 2 — Enrichissement via LLM (si nom inconnu)
    enrichment_prompt = f"""
You are an expert in piano manufacturers.

The user entered: "{brand}".

Please determine if this is a real piano or musical instrument brand.

👉 If it is **not** related to pianos or instruments (e.g., it's a car, tech, or clothing brand), return:
{{ "error": "Not a piano brand. Ask the user to confirm or upload a photo." }}

👉 Otherwise, return a valid JSON with these fields:
- brand
- country
- city
- years_active
- acquired_by (or null)
- notes: including historical facts, innovations, known pianists (e.g. Debussy)

💡 Output strictly valid JSON. Do not include markdown or explanation.

Example:

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

        # Extraire le JSON retourné (avec ou sans bloc ```json)
        match = re.search(r"{[\s\S]+}", response)
        raw_json = match.group(0) if match else response.strip()
        parsed = json.loads(raw_json)

        if "error" in parsed:
            return {
                "status": "rejected",
                "original": brand,
                "reason": parsed["error"]
            }

        return {
            "status": "enriched",
            "original": brand,
            "corrected": parsed.get("brand", brand),
            "llm_data": parsed
        }

    except Exception as e:
        print("⚠️ LLM enrichment failed:", repr(e))
        if "ReadTimeout" in str(e) or "timed out" in str(e).lower():
            return {
                "status": "llm_timeout",
                "attempted_brand": brand
            }

    # Étape 3 — Correction orthographique simple
    correction_prompt = f"""
The user entered this brand name: "{brand}".
Try to guess the most likely correct piano manufacturer name.
Return only the corrected name in plain text (no formatting).
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

    # Échec total
    return {
        "status": "not_found",
        "attempted_brand": brand
    }
