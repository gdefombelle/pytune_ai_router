import asyncio
from typing import Dict, Optional
from uuid import UUID
from fastapi import Request, HTTPException
from pytune_auth_common.models.schema import UserOut
from pytune_llm.task_reporting.reporter import TaskReporter
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
import re
from app.utils.normalize_piano_data import normalize_piano_data
from pytune_configuration import SimpleConfig, config

from app.core.prompt_builder import load_prompt_template_source

config = config or SimpleConfig()

def normalize_chat_history(raw_history: list) -> list:
    return [
        {"role": m["role"], "content": m["content"]}
        for m in raw_history
        if isinstance(m, dict) and m.get("role") in ("user", "assistant")
    ]

def is_identification_complete(first_piano: dict) -> bool:
    return (
        first_piano.get("brand")
        and first_piano.get("category")
        and (first_piano.get("size_cm") or first_piano.get("model") or first_piano.get("type"))
        and (first_piano.get("serial_number") or first_piano.get("year_estimated"))
        and first_piano.get("confirmed") is True
    ) # type: ignore

def should_transition_to_conversation(
    first_piano: dict,
    confirmed: bool | None = None,
) -> bool:
    is_confirmed = (
        confirmed is True
        or first_piano.get("confirmed") is True
    )

    return (
        is_confirmed
        and first_piano.get("brand")
        and first_piano.get("category")
        and (first_piano.get("model") or first_piano.get("size_cm") or first_piano.get("type"))
        and (first_piano.get("serial_number") or first_piano.get("year_estimated"))
    )  # type: ignore type: ignore

async def piano_agent_handler(
    agent_name: str,
    user_message: str,
    context: dict,
    reporter: Optional[TaskReporter],
) -> AgentResponse:

    conversation_id_str = context.get("conversation_id")
    first_piano = context.get("first_piano", {})

    # ============================================
    # 🧭 TRANSITION VERS CONVERSATION LIBRE
    # ============================================
    snapshot_fp = (
        context.get("agent_form_snapshot", {}).get("first_piano")
        if isinstance(context.get("agent_form_snapshot"), dict)
        else {}
    )

    confirmed_effective = (
        snapshot_fp.get("confirmed")
        if snapshot_fp is not None
        else first_piano.get("confirmed")
    )

    is_skip_upload = user_message.strip() == "__trigger_event__:skip_upload"

    if should_transition_to_conversation(first_piano, confirmed_effective) or is_skip_upload:
        enriched = enrich_context(context)

        if should_transition_to_conversation(enriched.get("first_piano", {}), confirmed_effective):
            chat_history = []
            uuid_ = None

            if conversation_id_str:
                try:
                    uuid_ = UUID(conversation_id_str)
                    raw_history = await get_conversation_history(uuid_)
                    chat_history = normalize_chat_history(raw_history)
                except Exception as e:
                    print("⚠️ Could not fetch chat history:", e)

            enriched["chat_history"] = chat_history
            template_source = load_prompt_template_source(
                "prompt_piano_agent_conversation.j2"
            )
            return_text = await run_chat_turn(
                template_source=template_source,
                context=enriched,
                history=chat_history,
                user_input="" if is_skip_upload else user_message,
                model=config.LLM_DEFAULT_MODEL,
                backend=config.LLM_BACKEND,
                reporter=reporter,
            )

            # ============================================
            # 🚨 OFF TOPIC (conversation libre)
            # ============================================
            if return_text and return_text.strip() == "[OFF_TOPIC]":
                return AgentResponse(
                    message="⚠️ I can only talk about your piano, music, or your playing. Let’s stay there.",
                    context_update={
                        "metadata": {"off_topic": True}
                    },
                    actions=[],
                    status="off_topic",
                )

            # ✅ Réponse normale
            return AgentResponse(
                message=return_text,
                context_update=None,
                actions=[],
            )

    # ============================================
    # 🧠 MODE AGENT GUIDÉ (POLICY)
    # ============================================

    response = await load_policy_and_resolve(agent_name, context, reporter=reporter)

    # ============================================
    # 🔍 EXTRACTION STRUCTURÉE (fallback LLM)
    # ============================================

    if not response.context_update or not response.context_update.get("first_piano"):
        try:
            extracted = extract_structured_piano_data(response.message or "")
            if extracted:
                extracted_fp = extracted.get("first_piano") or extracted
                merged_fp = merge_first_piano_data(
                    context.get("first_piano", {}),
                    extracted_fp
                )

                response.context_update = {
                    "first_piano": merged_fp,
                    "confidences": extracted.get("confidences", {}),
                    "metadata": {
                        **(response.context_update or {}).get("metadata", {}),
                        **extracted.get("metadata", {}),
                        "extracted_from_llm_output": True,
                    },
                }
        except Exception as e:
            print("⚠️ Failed to extract structured piano data:", e)

    # ============================================
    # 🧹 CLEANUP + MERGE FINAL
    # ============================================

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

    # ============================================
    # 🧼 STRIP JSON TRAILER FROM MESSAGE
    # ============================================

    if response.message:
        match = re.search(r"^(.*?)\n?{[\s\S]+}", response.message.strip())
        if match:
            response.message = match.group(1).strip()

    # ============================================
    # 💾 STORE CHAT HISTORY
    # ============================================

    if conversation_id_str:
        try:
            uuid_ = UUID(conversation_id_str)
            if user_message:
                await append_message(uuid_, "user", user_message)
            if response.message:
                await append_message(uuid_, "assistant", response.message)
        except Exception as e:
            print("⚠️ Failed to store chat history:", e)

    # ============================================
    # 🚨 OFF TOPIC (conversation mode)
    # ============================================
    if response.message and response.message.strip().startswith("[OFF_TOPIC]"):
        response.context_update = response.context_update or {}
        response.context_update.setdefault("metadata", {})["off_topic"] = True
        response.message = None          # ⛔ ne rien afficher
        response.actions = []
        response.status = "off_topic"
        return response
    # ============================================
    # 🔧 DOMAIN ENRICHMENT (brand / model / year)
    # ============================================

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
        reporter and await reporter.step("🔍 Resolving brand")
        brand_info = await resolve_brand_fields(brand, email, reporter=reporter)
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
        year_info = await resolve_serial_year(first_piano, manufacturer_id, corrected or brand, reporter=reporter)
        if year_info:
            context_update["first_piano"].update(year_info)

    if manufacturer_id and first_piano.get("model"):
        reporter and await reporter.step("🔧 Resolving model") # type: ignore
        lang = context.get("user_lang") or "en"
        model_info = await resolve_model_fields(
            first_piano,
            manufacturer_id,
            reporter=reporter,
            lang=lang
        )

        if "first_piano" in model_info:
            enriched_fp = model_info["first_piano"]
            existing_fp = context_update.setdefault("first_piano", {})
            for key, value in enriched_fp.items():
                if value is not None and (key not in existing_fp or existing_fp[key] in [None, "", 0]):
                    existing_fp[key] = value

        if "model_resolution" in model_info:
            context_update.setdefault("metadata", {})["model_resolution"] = model_info["model_resolution"]

        message = model_info.get("message", "")
        llm_notes = model_info.get("model_resolution", {}).get("llm_data", {}).get("notes")

        if llm_notes and llm_notes not in message:
            message += "\n\n" + llm_notes

        if model_info.get("message"):
            response.message = model_info["message"]

        if model_info.get("actions"):
            response.actions = model_info["actions"]

        response.context_update = context_update

    if "first_piano" in context_update:
        finalize_response_message(
            response,
            context_update,
            context.get("user_lang") or context.get("language") or "en"
        )

    return response