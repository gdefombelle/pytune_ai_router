from app.services.model_resolver import resolve_model_name
from app.services.type_resolver import resolve_type

CATEGORY_MAP = {
    1: "grand", 2: "upright",
    "1": "grand", "2": "upright"
}


async def resolve_model_fields(first_piano: dict, manufacturer_id: int) -> dict:
    model = first_piano.get("model")
    if not model:
        return {}

    model_result = await resolve_model_name(model, manufacturer_id)
    update = {
        "model_resolution": model_result,
    }

    if model_result["status"] == "found":
        update["first_piano"] = {
            "model_id": model_result["id"],
            "type": model_result.get("type"),
            "size_cm": model_result.get("size_cm"),
            "category": model_result.get("kind"),
            "source_model": model_result.get("source", "database")
        }

        # 🧼 Normalize category
        raw_cat = update["first_piano"].get("category")
        if raw_cat:
            update["first_piano"]["category"] = CATEGORY_MAP.get(raw_cat, raw_cat)

        # 🧩 Infer type if missing
        if not update["first_piano"].get("type"):
            resolved_type = resolve_type(
                update["first_piano"].get("category"),
                update["first_piano"].get("size_cm")
            )
            if resolved_type:
                update["first_piano"]["type"] = resolved_type

    elif model_result["status"] == "enriched":
        update["first_piano"] = {
            "model": model_result.get("corrected", model),
            "type": model_result["llm_data"].get("type"),
            "size_cm": model_result["llm_data"].get("size_cm"),
            "category": model_result["llm_data"].get("category"),
            "source_model": "llm"
        }

        # 🧼 Normalize category
        raw_cat = update["first_piano"].get("category")
        if raw_cat:
            update["first_piano"]["category"] = CATEGORY_MAP.get(raw_cat, raw_cat)

        if not update["first_piano"].get("type"):
            resolved_type = resolve_type(
                update["first_piano"].get("category"),
                update["first_piano"].get("size_cm")
            )
            if resolved_type:
                update["first_piano"]["type"] = resolved_type

    elif model_result["status"] == "rejected":
        update["first_piano"] = {
            "model": "",
        }
        update["message"] = (
            f"⚠️ The model **{model}** wasn’t found in our database.\n"
            f"You can upload a photo of the nameplate or keyboard area, or just skip this step."
        )
        update["actions"] = [
            {"suggest_action": "📸 Upload a photo", "trigger_event": "trigger_upload"},
            {"suggest_action": "Skip this step", "trigger_event": "set_model_dont_know"}
        ]

    return update
