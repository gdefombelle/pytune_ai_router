from typing import Optional, Dict

from app.utils.dontknow_utils import humanize_dont_know_list
from app.services.piano_extract import make_readable_message_from_extraction
from .piano_extract import render_warnings, resolve_type
from .model_resolver import resolve_model_name
from .brand_resolver import resolve_brand_name
from .age_resolver import resolve_age


async def resolve_model_fields(first_piano: dict, manufacturer_id: int) -> dict:
    model = first_piano.get("model")
    if not model:
        return {}

    model_result = await resolve_model_name(model, first_piano, manufacturer_id)

    update = {
        "model_resolution": model_result,  # ✅ Toujours renvoyé
    }

    message_parts = []

    # ✅ Cas 1 : modèle trouvé dans la base
    if model_result["status"] == "found":
        update["first_piano"] = {
            "model": model_result.get("matched_name", model),
            "type": model_result.get("type"),
            "size_cm": model_result.get("size_cm"),
            "category": model_result.get("kind"),
            "source_model": model_result.get("source", "database")
        }

        if "id" in model_result:
            update["first_piano"]["model_id"] = model_result["id"]

        if not update["first_piano"].get("type"):
            resolved_type = resolve_type(
                model_result.get("kind"),
                model_result.get("size_cm")
            )
            if resolved_type:
                update["first_piano"]["type"] = resolved_type

        # 💬 Ajout des notes si dispo
        notes = model_result.get("llm_data", {}).get("notes")
        if notes:
            message_parts.append(notes)

    # ✅ Cas 2 : enrichi via LLM
    elif model_result["status"] == "enriched":
        llm_data = model_result["llm_data"]
        update["first_piano"] = {
            "model": model_result.get("corrected", model),
            "type": llm_data.get("type"),
            "size_cm": llm_data.get("size_cm"),
            "category": llm_data.get("category"),
            "source_model": "llm"
        }

        if not update["first_piano"].get("type"):
            resolved_type = resolve_type(
                llm_data.get("category"),
                llm_data.get("size_cm")
            )
            if resolved_type:
                update["first_piano"]["type"] = resolved_type

        # 💬 Ajout des notes LLM si présentes
        notes = llm_data.get("notes")
        if notes:
            message_parts.append(notes)

    # ✅ Cas 3 : rejeté ou non documenté
    elif model_result["status"] in ["rejected", "not_found"]:
        update["first_piano"] = {
            "model": model,
            "source_model": "rejected_by_llm"
        }

        base_message = (
            f"⚠️ The model **{model}** wasn’t found in our database.\n"
            f"You can upload a photo of the nameplate or keyboard area, or just skip this step."
        )
        message_parts.append(base_message)

        # 💬 Ajout des notes LLM même si rejected
        llm_notes = model_result.get("llm_data", {}).get("notes")
        if llm_notes:
            message_parts.append(llm_notes)

        update["actions"] = [
            {"suggest_action": "📸 Upload a photo", "trigger_event": "trigger_upload"},
            {"suggest_action": "Skip this step", "trigger_event": "set_model_dont_know"}
        ]

    # ✅ Assemble le message final s’il y a des choses à dire
    if message_parts:
        update["message"] = "\n\n".join(part.strip() for part in message_parts if part)

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
    meta = context_update.get("metadata", {}) or {}
    acknowledged = meta.get("acknowledged")
    brand_resolution = context_update.get("brand_resolution")

    # 🔒 Cas 1 – message déjà défini mais il contient du JSON → on le remplace
    if response.message and response.message.strip().startswith("{"):
        response.message = make_readable_message_from_extraction(context_update, brand_resolution)

    # 🔒 Cas 2 – message vide + ack dont_know
    elif not response.message and acknowledged:
        flags = acknowledged if isinstance(acknowledged, list) else [acknowledged]
        readable = humanize_dont_know_list(flags)
        if readable:
            response.message = f"✅ Got it — {readable}, we can skip it for now."
            return

    # 🔒 Cas 3 – message vide tout court
    elif not response.message:
        response.message = make_readable_message_from_extraction(context_update, brand_resolution)

    # ✅ Ajout final des avertissements éventuels
    warning_text = render_warnings(meta)
    if warning_text:
        response.message += warning_text

