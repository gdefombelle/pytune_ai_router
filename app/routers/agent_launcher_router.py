import asyncio
from typing import Any, Dict
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Request, Body
from pytune_chat.store import get_conversation_history
from app.core.policy_loader import load_policy_and_resolve, load_yaml
from app.core.context_resolver import resolve_user_context
from app.core.context_enrichment import enrich_context
from pytune_auth_common.models.schema import UserOut
from pytune_auth_common.services.auth_checks import get_current_user
from app.models.policy_model import AgentResponse
from pytune_chat.store import append_message

# ✅ Handlers spécialisés
from app.handlers.piano_agent_handler import (
    piano_agent_handler,
    piano_agent_start_handler
)
from app.utils.context_helpers import prepare_enriched_context
from app.utils.piano_merge import merge_first_piano_data

router = APIRouter(prefix="/ai/agents", tags=["AI Agents"])

@router.post("/{agent_name}/start", response_model=AgentResponse)
async def start_agent(
    agent_name: str,
    extra_context: dict = Body(..., embed=True),
    user: UserOut = Depends(get_current_user),
):
    policy = load_yaml(agent_name)
    use_memory = policy.get("metadata", {}).get("memory") is True

    # 🧠 Si mémoire activée, créer une conversation
    conversation_id = None
    if use_memory:
        from pytune_chat.store import create_conversation
        conv = await create_conversation(user.id, topic=agent_name)
        conversation_id = str(conv.id)

    # 🔧 Résolution du contexte utilisateur enrichi
    full_context = await resolve_user_context(user, extra=extra_context)
    enriched_context = enrich_context(full_context)

    # 🧠 Injecter le conversation_id si présent
    if conversation_id:
        enriched_context["conversation_id"] = conversation_id

    # 🚀 Appelle le moteur de policy (avec bloc start si applicable)
    response = await load_policy_and_resolve(agent_name, enriched_context)

    # 📝 Historise le message initial assistant si applicable
    if conversation_id and response.message:
        from pytune_chat.store import append_message
        try:
            await append_message(UUID(conversation_id), "assistant", response.message)
        except Exception as e:
            print(f"⚠️ Failed to log initial assistant message: {e}")

    # 📦 Retourne la conversation_id au client
    if conversation_id:
        response.meta = {
            **response.meta,
            "conversation_id": conversation_id
        }

    return response


@router.post("/{agent_name}/evaluate", response_model=AgentResponse)
async def evaluate_agent(
    agent_name: str,
    request: Request,
    user: UserOut = Depends(get_current_user),
):
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    extra_context = payload.get("extra_context", {})
    conversation_id = extra_context.get("conversation_id")
    first_piano = extra_context.get("first_piano", {})
    confirmed = first_piano.get("confirmed") is True

    if confirmed:
        print("🧪 Simulating piano save (from /evaluate)...")
        await asyncio.sleep(0.8)
        return AgentResponse(
            message="✅ Your piano has been successfully saved.\n"
                    "Would you like to upload photos of it (optional)? Click ➕",
            actions=[{"suggest_action": "Skip this step", "trigger_event": "skip_upload"}],
            context_update={"first_piano": {"confirmed": True}}
        )

    # 🔁 Construction enrichie du contexte complet
    full_extra = {
        **extra_context,
        "user_input": "",
        "raw_user_input": "",
        "conversation_id": conversation_id,
    }

    context = await resolve_user_context(user, extra=full_extra)
    enriched_context = enrich_context(context)

    # ✅ Fusion non destructive des données snapshot
    snapshot_fp = extra_context.get("agent_form_snapshot", {}).get("first_piano")
    if snapshot_fp:
        enriched_context["first_piano"] = merge_first_piano_data(
            enriched_context.get("first_piano", {}),
            snapshot_fp
        )

    response = await load_policy_and_resolve(agent_name, enriched_context)

    if conversation_id and response.message:
        try:
            uuid_ = UUID(conversation_id)
            await append_message(uuid_, "assistant", response.message)
        except Exception as e:
            print(f"⚠️ Failed to append assistant message from /evaluate: {e}")

    return response

@router.post("/{agent_name}/message", response_model=AgentResponse)
async def agent_message(
    agent_name: str,
    request: Request,
    user: UserOut = Depends(get_current_user),
):
    payload = await request.json()
    message = payload.get("message", "")
    extra_context = payload.get("extra_context", {})

    # 🧠 Centralise ici le contexte enrichi
    context = await prepare_enriched_context(user, agent_name, message, extra_context)

    if agent_name == "piano_agent":
        ret = await piano_agent_handler(agent_name, message, context)
        return ret

    return await load_policy_and_resolve(agent_name, context)
