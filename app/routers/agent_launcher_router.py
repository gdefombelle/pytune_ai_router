from typing import Any, Dict
from fastapi import APIRouter, Depends, HTTPException, Request, Body
from app.core.policy_loader import load_policy_and_resolve, load_yaml
from app.core.context_resolver import resolve_user_context
from app.core.context_enrichment import enrich_context
from pytune_auth_common.models.schema import UserOut
from pytune_auth_common.services.auth_checks import get_current_user
from app.models.policy_model import AgentResponse

# ✅ Handlers spécialisés
from app.handlers.piano_agent_handler import (
    piano_agent_handler,
    piano_agent_start_handler
)

router = APIRouter(prefix="/ai/agents", tags=["AI Agents"])


@router.post("/{agent_name}/start", response_model=AgentResponse)
async def start_agent(
    agent_name: str,
    extra_context: dict = Body(..., embed=True),
    user: UserOut = Depends(get_current_user),
):
    policy = load_yaml(agent_name)
    use_memory = policy.get("metadata", {}).get("memory") is True

    conversation_id = None
    if use_memory:
        from pytune_chat.store import create_conversation
        conv = await create_conversation(user.id, topic=agent_name)
        conversation_id = str(conv.id)

    if agent_name == "piano_agent":
        return await piano_agent_start_handler(
             agent_name, extra_context, user, conversation_id
        )

    full_context = await resolve_user_context(user, extra=extra_context)
    enriched_context = enrich_context(full_context)

    response = await load_policy_and_resolve(agent_name, enriched_context)

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
    conversation_id = payload.get("conversation_id")

    # 🧠 On simule un message vide mais explicite
    full_extra = {
        **extra_context,
        "user_input": "",
        "raw_user_input": "",
        "conversation_id": conversation_id,
    }

    context = await resolve_user_context(user, extra=full_extra)
    enriched_context = enrich_context(context)
    return await load_policy_and_resolve(agent_name, enriched_context)



@router.post("/{agent_name}/message", response_model=AgentResponse)
async def agent_message(
    agent_name: str,
    request: Request,
    user: UserOut = Depends(get_current_user),
):
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    if agent_name == "piano_agent":
        return await piano_agent_handler(agent_name=agent_name, payload=payload, user=user)

    # fallback générique
    user_message = payload.get("message", "")
    extra_context = payload.get("extra_context", {})

    full_extra = {
        **extra_context,
        "user_input": user_message,
        "raw_user_input": user_message
    }

    context = await resolve_user_context(user, extra=full_extra)
    enriched_context = enrich_context(context)
    return await load_policy_and_resolve(agent_name, enriched_context)
