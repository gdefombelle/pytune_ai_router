from typing import Optional, Dict

from app.utils.dontknow_utils import humanize_dont_know_list
from app.services.piano_extract import make_readable_message_from_extraction
from .piano_extract import resolve_type
from .model_resolver import resolve_model_name
from .brand_resolver import resolve_brand_name
from .age_resolver import resolve_age


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

        if not update["first_piano"].get("type"):
            resolved_type = resolve_type(
                model_result.get("kind"),
                model_result.get("size_cm")
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

        if not update["first_piano"].get("type"):
            resolved_type = resolve_type(
                model_result["llm_data"].get("category"),
                model_result["llm_data"].get("size_cm")
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


async def resolve_brand_fields(brand: str, email: str) -> dict:
    result = await resolve_brand_name(brand, email)
    corrected = (
        result.get("matched_name") or
        result.get("corrected") or
        result.get("llm_data", {}).get("brand")
    )
    manufacturer_id = (
        result.get("matched_id") or
        result.get("manufacturer_id") or
        result.get("id")
    )
    return {
        "brand_resolution": result,
        "corrected": corrected,
        "manufacturer_id": manufacturer_id
    }


async def resolve_serial_year(first_piano: dict, manufacturer_id: Optional[int], brand: Optional[str]) -> dict:
    serial = first_piano.get("serial_number")
    if not manufacturer_id:
        return {}

    year, confidence, source = await resolve_age(
        manufacturer_id=manufacturer_id,
        serial_number=serial,
        brand_name=brand
    )

    if year:
        return {
            "year_estimated": year,
            "year_estimated_confidence": confidence,
            "year_estimated_source": source
        }
    return {}


def finalize_response_message(response, context_update):
    if not response.message:
        meta = context_update.get("metadata", {})
        acknowledged = meta.get("acknowledged")
        if acknowledged:
            flags = acknowledged if isinstance(acknowledged, list) else [acknowledged]
            readable = humanize_dont_know_list(flags)
            if readable:
                response.message = f"✅ Got it — {readable}, we can skip it for now."
    else:
        response.message = make_readable_message_from_extraction(
            context_update,
            brand_resolution=context_update.get("brand_resolution")
        )
