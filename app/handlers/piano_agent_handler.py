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
from app.utils.piano_extract import extract_structured_piano_data, make_readable_message_from_extraction
from app.services.type_resolver import resolve_type
from app.utils.piano_merge import merge_first_piano_data
from app.core.context_enrichment import enrich_context_with_brands
from app.utils.dontknow_utils import humanize_dont_know_list
from app.services.model_resolver import resolve_model_name

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
        response.context_update["first_piano"] = merged_fp

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
    serial = first_piano.get("serial_number")
    email = context.get("email", "")
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

    model = first_piano.get("model")
    if manufacturer_id and model:
        model_result = await resolve_model_name(model, manufacturer_id)
        context_update.setdefault("metadata", {})["model_resolution"] = model_result

        if model_result["status"] == "found":
            context_update["first_piano"].update({
                "model_id": model_result["id"],
                "type": model_result.get("type"),
                "size_cm": model_result.get("size_cm"),
                "category": model_result.get("kind"),
                "source_model": model_result.get("source", "database")
            })

            resolved_type = resolve_type(model_result.get("kind"), model_result.get("size_cm"))
            if resolved_type and not context_update["first_piano"].get("type"):
                context_update["first_piano"]["type"] = resolved_type

        elif model_result["status"] == "enriched":
            context_update["first_piano"].update({
                "model": model_result.get("corrected", model),
                "type": model_result["llm_data"].get("type"),
                "size_cm": model_result["llm_data"].get("size_cm"),
                "category": model_result["llm_data"].get("category"),
                "source_model": "llm"
            })

            resolved_type = resolve_type(
                model_result["llm_data"].get("category"),
                model_result["llm_data"].get("size_cm")
            )
            if resolved_type and not context_update["first_piano"].get("type"):
                context_update["first_piano"]["type"] = resolved_type

        elif model_result["status"] == "rejected":
            context_update["first_piano"]["model"] = ""
            response.message = (
                f"⚠️ The model **{model}** wasn’t found in our database.\n"
                f"You can upload a photo of the nameplate or keyboard area, or just skip this step."
            )
            response.actions = [
                {"suggest_action": "📸 Upload a photo", "trigger_event": "trigger_upload"},
                {"suggest_action": "Skip this step", "trigger_event": "set_model_dont_know"}
            ]

    response.context_update = context_update

    if response.context_update and "first_piano" in response.context_update:
        if not response.message:
            meta = response.context_update.get("metadata", {})
            acknowledged = meta.get("acknowledged")
            if acknowledged:
                flags = acknowledged if isinstance(acknowledged, list) else [acknowledged]
                readable = humanize_dont_know_list(flags)
                if readable:
                    response.message = f"✅ Got it — {readable}, we can skip it for now."
        else:
            response.message = make_readable_message_from_extraction(
                response.context_update,
                brand_resolution=response.context_update.get("brand_resolution")
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