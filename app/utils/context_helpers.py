from uuid import UUID
from pytune_auth_common.models.schema import UserOut
from pytune_chat.store import get_conversation_history

from app.core.context_resolver import resolve_user_context
from app.core.context_enrichment import enrich_context


async def prepare_enriched_context(
    user: UserOut,
    agent_name: str,
    message: str,
    extra_context: dict,
) -> dict:
    convo_id = extra_context.get("conversation_id")
    full_extra = {
        **extra_context,
        "user_input": message,
        "raw_user_input": message,
        "conversation_id": convo_id,
    }    # 🧠 Ajout last_prompt à l’extra context
    # 🧠 Ajout last_prompt à l’extra context
    if convo_id:
        try:
            uuid_ = UUID(convo_id)
            history = await get_conversation_history(uuid_)
            last_prompt = next((m["content"] for m in reversed(history) if m["role"] == "assistant"), None)
            if last_prompt:
                full_extra["last_prompt"] = last_prompt
        except Exception as e:
            print(f"⚠️ Failed to get last_prompt: {e}")




    context = await resolve_user_context(user, extra=full_extra)
    context = enrich_context(context)
    return context

def build_context_snapshot(result: dict, manufacturer_id: int) -> dict:
    return {
        "manufacturer_id": manufacturer_id,
        "age_method": result.get("age_method"),
        "source": "photos.identify",
        "inferred_scene": result.get("extra", {}).get("scene_description"),
        "sheet_music": result.get("extra", {}).get("sheet_music"),
        "estimated_value_eur": result.get("extra", {}).get("estimated_value_eur"),
        "value_confidence": result.get("extra", {}).get("value_confidence"),
    }

def build_model_data(result: dict) -> dict:
    sheet_music = result.get("extra", {}).get("sheet_music") or {}
    return {
        "brand": result.get("brand"),
        "distributor": result.get("distributor"),
        "serial_number": result.get("serial_number"),
        "year_estimated": result.get("age"),
        "category": result.get("category"),
        "type": result.get("type"),
        "size_cm": result.get("size_cm"),
        "nb_notes": result.get("nb_notes"),
        "sheet_music": sheet_music.get("title"),
        "scene_description": result.get("extra", {}).get("scene_description"),
        "photos": result.get("extra", {}).get("photos", []),
    }
