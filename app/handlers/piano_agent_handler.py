from uuid import UUID
from fastapi import Request, HTTPException
from pytune_auth_common.models.schema import UserOut
from app.models.policy_model import AgentResponse
from app.core.context_resolver import resolve_user_context
from app.core.context_enrichment import enrich_context
from app.core.policy_loader import load_yaml, load_policy_and_resolve
from pytune_chat.orchestrator import run_chat_turn
from pytune_chat.store import append_message, create_conversation
from app.services.brand_resolver import resolve_brand_name
from app.services.age_resolver import resolve_age

async def piano_agent_handler(agent_name: str, payload: dict, user: UserOut) -> AgentResponse:
    user_message = payload.get("message", "")
    extra_context = payload.get("extra_context", {})
    conversation_id_str = payload.get("conversation_id")

    full_extra = {
        **extra_context,
        "user_input": user_message,
        "raw_user_input": user_message
    }

    context = await resolve_user_context(user, extra=full_extra)
    enriched_context = enrich_context(context)

    policy_data = load_yaml(agent_name)
    use_memory = policy_data.get("metadata", {}).get("memory") is True

    response = await load_policy_and_resolve(agent_name, enriched_context)

    # 🔍 Traitement spécifique : vérif marque + datation
    context_update = response.context_update or {}
    first_piano = context_update.get("first_piano", {})
    brand = first_piano.get("brand")
    serial = first_piano.get("serial_number")
    email = enriched_context.get("email", "")

    manufacturer_id = None

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

    # 🗕️ Résolution de l'année — même si pas de numéro de série
    if manufacturer_id:
        resolved = await resolve_age( manufacturer_id=manufacturer_id, serial_number=serial, brand_name=corrected or brand)
        if resolved:
            context_update["first_piano"].update(resolved)

    response.context_update = context_update

    # 💾 Ajout mémoire si activée
    if use_memory and conversation_id_str:
        conversation_id = UUID(conversation_id_str)
        is_fallback = not response.context_update and "${" not in response.message

        if is_fallback:
            llm_response = await run_chat_turn(conversation_id, user_message)
            await append_message(conversation_id, "user", user_message)
            await append_message(conversation_id, "assistant", llm_response)
            response.message = llm_response
            return response

        await append_message(conversation_id, "user", user_message)
        await append_message(conversation_id, "assistant", response.message)

    return response


async def piano_agent_start_handler(agent_name: str, extra_context: dict, user: UserOut) -> AgentResponse:
    context = await resolve_user_context(user, extra=extra_context)
    enriched_context = enrich_context(context)

    policy = load_yaml(agent_name)
    use_memory = policy.get("metadata", {}).get("memory") is True

    conversation_id = None
    if use_memory:
        conv = await create_conversation(user.id, topic=agent_name)
        conversation_id = str(conv.id)

    response = await load_policy_and_resolve(agent_name, enriched_context)

    # Traitement des marque + age ≈ comme dans handler
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
