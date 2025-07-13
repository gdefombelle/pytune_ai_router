import asyncio
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
from app.services.piano_extract import extract_structured_piano_data, make_readable_message_from_extraction
from app.services.type_resolver import resolve_type
from app.utils.piano_merge import merge_first_piano_data
from app.core.context_enrichment import enrich_context_with_brands
from app.utils.dontknow_utils import humanize_dont_know_list, clean_dont_know_flags
from app.services.model_resolver import resolve_model_name
from app.services.piano_logic import (
    resolve_model_fields,
    resolve_brand_fields,
    resolve_serial_year,
    finalize_response_message
)

def is_identification_complete(first_piano: dict) -> bool:
    return (
        first_piano.get("brand")
        and first_piano.get("category")
        and (first_piano.get("size_cm") or first_piano.get("model") or first_piano.get("type"))
        and (first_piano.get("serial_number") or first_piano.get("year_estimated"))
        and first_piano.get("confirmed") is True
    )

async def piano_agent_handler(agent_name: str, user_message: str, context: dict) -> AgentResponse:


    conversation_id_str = context.get("conversation_id")
    first_piano = context.get("first_piano", {})

    if user_message == "__trigger_event__:save_piano":
        print("🧪 Simulating piano save...")
        await asyncio.sleep(0.8)
        return AgentResponse(
            message="✅ Your piano has been successfully saved.",
            actions=[
                {"suggest_action": "Upload photos", "trigger_event": "trigger_upload"},
                {"suggest_action": "Skip this step", "trigger_event": "skip_upload"}
            ],
            context_update={"first_piano": {"confirmed": True}}
        )

    if is_identification_complete(first_piano):
        chat_history = []
        if conversation_id_str:
            try:
                uuid_ = UUID(conversation_id_str)
                chat_history = await get_conversation_history(uuid_)
            except Exception as e:
                print("⚠️ Could not fetch chat history:", e)

        convo_messages = [
            {"role": m.role, "content": m.content}
            for m in chat_history if m.role in ("user", "assistant")
        ]
        context["chat_history"] = convo_messages

        return await run_chat_turn(
            user_input=user_message,
            prompt_name="prompt_piano_agent_conversation.j2",
            context=context,
            model="gpt-3.5-turbo"
        )

    response = await load_policy_and_resolve(agent_name, context)

    if not response.context_update or not response.context_update.get("first_piano"):
        try:
            extracted = extract_structured_piano_data(response.message or "")
            if extracted:
                extracted_fp = extracted.get("first_piano") or extracted
                existing_fp = context.get("first_piano", {})
                merged_fp = merge_first_piano_data(existing_fp, extracted_fp)

                existing_meta = response.context_update.get("metadata", {}) if response.context_update else {}
                extracted_meta = extracted.get("metadata", {})

                response.context_update = {
                    "first_piano": merged_fp,
                    "confidences": extracted.get("confidences", {}),
                    "metadata": {
                        **existing_meta,
                        **extracted_meta,
                        "extracted_from_llm_output": True
                    }
                }
        except Exception as e:
            print("⚠️ Failed to extract structured piano data:", e)

    if response.context_update and "first_piano" in response.context_update:
        merged_fp = merge_first_piano_data(
            context.get("first_piano", {}),
            response.context_update["first_piano"]
        )
        cleaned_fp, cleaned_meta = clean_dont_know_flags(
            merged_fp,
            response.context_update.get("metadata", {})
        )
        response.context_update["first_piano"] = cleaned_fp
        response.context_update["metadata"] = cleaned_meta

    if conversation_id_str:
        try:
            uuid_ = UUID(conversation_id_str)
            if user_message:
                await append_message(uuid_, "user", user_message)
            if response.message:
                await append_message(uuid_, "assistant", response.message)
        except Exception as e:
            print("⚠️ Failed to store chat history:", e)

    if response.context_update and response.context_update.get("metadata", {}).get("off_topic"):
        response.status = "off_topic"
        response.actions = []
        return response

    context_update = response.context_update or {}
    first_piano = context_update.get("first_piano", {})
    brand = first_piano.get("brand")
    email = context.get("email", "")
    manufacturer_id = None

    if first_piano.get("category") and first_piano.get("size_cm") and not first_piano.get("type"):
        inferred_type = resolve_type(first_piano["category"], first_piano["size_cm"])
        if inferred_type:
            context_update["first_piano"]["type"] = inferred_type

    if brand:
        brand_info = await resolve_brand_fields(brand, email)
        context_update["brand_resolution"] = brand_info["brand_resolution"]
        manufacturer_id = brand_info["manufacturer_id"]
        corrected = brand_info["corrected"]

        if brand_info["brand_resolution"]["status"] == "rejected":
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
        year_info = await resolve_serial_year(first_piano, manufacturer_id, corrected or brand)
        if year_info:
            context_update["first_piano"].update(year_info)

    if manufacturer_id and first_piano.get("model"):
        model_info = await resolve_model_fields(first_piano, manufacturer_id)
        if "first_piano" in model_info:
            context_update["first_piano"].update(model_info["first_piano"])
        if "model_resolution" in model_info:
            context_update.setdefault("metadata", {})["model_resolution"] = model_info["model_resolution"]
        if "message" in model_info:
            response.message = model_info["message"]
        if "actions" in model_info:
            response.actions = model_info["actions"]

    response.context_update = context_update
    if response.context_update and "first_piano" in response.context_update:
        finalize_response_message(response, response.context_update)


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