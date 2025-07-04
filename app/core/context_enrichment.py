from typing import Dict, Any

from pytune_data.piano_data_service import get_all_normalized_brands

def enrich_context(context: Dict[str, Any]) -> Dict[str, Any]:
    snapshot = context.get("agent_form_snapshot", {})
    # 🔁 Si c’est un snapshot structuré comme dans le front (first_piano imbriqué)
    if "first_piano" in snapshot:
        snapshot = snapshot["first_piano"]

    # Piano enrichments
    context["first_piano"] = {
        "brand": snapshot.get("brand", ""),
        "model": snapshot.get("model", ""),
        "serial_number": snapshot.get("serial_number", ""),
        "year_estimated": snapshot.get("year_estimated"),
        "category": snapshot.get("category"),
        "type": snapshot.get("type"),
        "size_cm": snapshot.get("size_cm"),
        "nb_notes": snapshot.get("nb_notes", 88),
    }

    context["no_piano"] = not context["first_piano"]["brand"]

    return context


async def enrich_context_with_brands(context: dict) -> dict:
    known_brands = await get_all_normalized_brands()
    context["known_brands"] = known_brands
    return context
