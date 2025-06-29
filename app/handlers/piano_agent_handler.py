from typing import Optional
from uuid import UUID
from fastapi import Request, HTTPException
from pytune_auth_common.models.schema import UserOut
from app.models.policy_model import AgentResponse
from app.core.context_resolver import resolve_user_context
from app.core.context_enrichment import enrich_context
from app.core.policy_loader import load_yaml, load_policy_and_resolve
from pytune_chat.orchestrator import run_chat_turn
from pytune_chat.store import append_message, create_conversation, get_conversation_history
from app.services.brand_resolver import resolve_brand_name
from app.services.age_resolver import resolve_age
from app.utils.piano_extract import extract_structured_piano_data, make_readable_message_from_extraction
from app.services.type_resolver import resolve_type
from app.utils.piano_merge import merge_first_piano_data

def is_identification_complete(first_piano: dict) -> bool:
    return (
        first_piano.get("brand")
        and first_piano.get("category")
        and (first_piano.get("size_cm") or first_piano.get("model") or first_piano.get("type"))
        and (first_piano.get("serial_number") or first_piano.get("year_estimated"))
        and first_piano.get("confirmed") is True
    )


async def piano_agent_handler(agent_name: str, payload: dict, user: UserOut) -> AgentResponse:
    user_message = payload.get("message", "")
    extra_context = payload.get("extra_context", {})
    conversation_id_str = extra_context.get("conversation_id")

    full_extra = {
        **extra_context,
        "user_input": user_message,
        "raw_user_input": user_message,
        "conversation_id": conversation_id_str,
    }

    context = await resolve_user_context(user, extra=full_extra)
    enriched_context = enrich_context(context)
    first_piano = enriched_context.get("first_piano", {})

    if is_identification_complete(first_piano):
        chat_history = []
        if conversation_id_str:
            uuid_ = UUID(conversation_id_str)
            chat_history = await get_conversation_history(uuid_)
        convo_messages = [
            {"role": m.role, "content": m.content}
            for m in chat_history if m.role in ("user", "assistant")
        ]
        context["chat_history"] = convo_messages
        prompt_template = "prompt_piano_agent_conversation.j2"
        response = await run_chat_turn(
            user_input=user_message,
            prompt_name=prompt_template,
            context=context,
            model="gpt-3.5-turbo",
        )
        return response

    response = await load_policy_and_resolve(agent_name, enriched_context)

    if not response.context_update or not response.context_update.get("first_piano"):
        try:
            extracted = extract_structured_piano_data(response.message or "")
            if extracted:
                extracted_fp = extracted.get("first_piano") if "first_piano" in extracted else extracted
                existing_fp = enriched_context.get("first_piano", {})
                merged_fp = merge_first_piano_data(existing_fp, extracted_fp)

                response.context_update = {
                    "first_piano": merged_fp,
                    "confidences": extracted.get("confidences", {}),
                    "metadata": {"extracted_from_llm_output": True}
                }
        except Exception as e:
            print("⚠️ Failed to extract structured piano data:", e)

    if conversation_id_str:
        conversation_id = UUID(conversation_id_str)
        if user_message:
            await append_message(conversation_id, "user", user_message)
        if response.message:
            await append_message(conversation_id, "assistant", response.message)

    if response.context_update and response.context_update.get("metadata", {}).get("off_topic"):
        response.status = "off_topic"
        response.actions = []
        return response

    context_update = response.context_update or {}
    first_piano = context_update.get("first_piano", {})
    brand = first_piano.get("brand")
    serial = first_piano.get("serial_number")
    email = enriched_context.get("email", "")
    manufacturer_id = None

    if first_piano.get("category") and first_piano.get("size_cm") and not first_piano.get("type"):
        inferred_type = resolve_type(first_piano["category"], first_piano["size_cm"])
        if inferred_type:
            context_update["first_piano"]["type"] = inferred_type

    corrected = None

    if brand:
        result = await resolve_brand_name(brand, email)
        context_update["brand_resolution"] = result
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
        if result["status"] == "rejected":
            response.message = (
                f"⚠️ The brand **{brand}** doesn’t appear to be a known piano manufacturer.\n"
                f"If you're unsure, please upload a photo of the piano’s logo or fallboard."
            )
            response.actions = [{
                "label": "📸 Upload a photo",
                "type": "upload",
                "target": "photo_upload"
            }]
            context_update["first_piano"]["brand"] = ""
        elif corrected and corrected != brand:
            context_update["first_piano"]["brand"] = corrected

    if manufacturer_id:
        year, confidence, source = await resolve_age(
            manufacturer_id=manufacturer_id,
            serial_number=serial,
            brand_name=corrected or brand
        )
        if year:
            context_update["first_piano"].update({
                "year_estimated": year,
                "year_estimated_confidence": confidence,
                "year_estimated_source": source
            })

    response.context_update = context_update

    # ✅ Dernier enrichissement du message à afficher (lisible)
    response.message = make_readable_message_from_extraction(
        context_update,
        brand_resolution=context_update.get("brand_resolution")
    )

    return response
async def piano_agent_start_handler(
    agent_name: str,
    extra_context: dict,
    user: UserOut,
    conversation_id: Optional[str] = None,
) -> AgentResponse:
    context = await resolve_user_context(user, extra=extra_context)
    enriched_context = enrich_context(context)

    policy = load_yaml(agent_name)

    response = await load_policy_and_resolve(agent_name, enriched_context)

    # Marque & datation
    context_update = response.context_update or {}
    first_piano = context_update.get("first_piano", {})
    brand = first_piano.get("brand")
    serial = first_piano.get("serial_number")
    email = enriched_context.get("email", "")

    if brand:
        result = await resolve_brand_name(brand, email)
        context_update["brand_resolution"] = result

        corrected = (
            result.get("matched_name") or
            result.get("corrected") or
            result.get("llm_data", {}).get("brand")
        )

        if result["status"] == "rejected":
            response.message = (
                f"\u26a0\ufe0f The brand **{brand}** doesn’t appear to be a known piano manufacturer.\n"
                f"If you're unsure, please upload a photo of the piano’s logo or fallboard."
            )
            response.actions = [{
                "label": "📸 Upload a photo",
                "type": "upload",
                "target": "photo_upload"
            }]
            context_update["first_piano"]["brand"] = ""

        elif corrected and corrected != brand:
            context_update["first_piano"]["brand"] = corrected
            response.message += (
                f"\n\n🔎 It looks like you meant **{corrected}** instead of **{brand}**. "
                "You can correct it below if needed, or upload a photo to confirm."
            )

    if brand and serial:
        resolved = await resolve_age(brand, serial)
        if resolved:
            context_update["first_piano"].update(resolved)

    response.context_update = context_update

    if conversation_id:
        response.meta = {
            **response.meta,
            "conversation_id": conversation_id
        }

    return response