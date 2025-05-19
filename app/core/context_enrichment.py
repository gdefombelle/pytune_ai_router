from typing import Dict, Any

def enrich_context(context: Dict[str, Any]) -> Dict[str, Any]:
    snapshot = context.get("agent_form_snapshot", {})

    # Piano enrichments
    context["first_piano"] = {
        "brand": snapshot.get("piano_brand", ""),
        "model": snapshot.get("piano_model", ""),
        "serial_number": snapshot.get("piano_serial_number", ""),
        "year_estimated": snapshot.get("piano_year_estimated"),
        "category": snapshot.get("piano_category"),
        "type": snapshot.get("piano_type"),
        "size_cm": snapshot.get("piano_size_cm"),
        "nb_notes": snapshot.get("piano_nb_notes", 88),
    }

    context["no_piano"] = not context["first_piano"]["brand"]

    return context
