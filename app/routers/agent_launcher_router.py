# app/routers/agent_launcher_router.py

from typing import Any, Dict
from fastapi import APIRouter, Depends, HTTPException, Request, Body
from app.core.policy_loader import load_policy_and_resolve
from app.core.context_resolver import resolve_user_context
from pytune_auth_common.models.schema import UserOut
from pytune_auth_common.services.auth_checks import get_current_user
from app.models.policy_model import AgentResponse
from fastapi import Request
from fastapi import Body
from app.core.context_enrichment import enrich_context

router = APIRouter(prefix="/ai/agents", tags=["AI Agents"])


@router.post("/{agent_name}/start", response_model=AgentResponse)
async def start_agent(
    agent_name: str,
    extra_context: dict = Body(..., embed=True),  # ✅ utilise embed=True
    user: UserOut = Depends(get_current_user),
):
   
    full_context = await resolve_user_context(user, extra=extra_context)
    enriched_context = enrich_context(full_context)
    return await load_policy_and_resolve(agent_name, enriched_context)


@router.post("/{agent_name}/evaluate", response_model=AgentResponse)
async def evaluate_agent(
    agent_name: str,
    body: dict = Body(default={}),
    user: UserOut = Depends(get_current_user),
):
    user_input = body.get("user_input", {})
    full_context = await resolve_user_context(user, extra=user_input)
    return await load_policy_and_resolve(agent_name, full_context)

@router.post("/{agent_name}/message", response_model=AgentResponse)
async def agent_message(
    agent_name: str,
    request: Request,
    user: UserOut = Depends(get_current_user),
):
    # ✅ Parse JSON manuellement (robuste)
    try:
        payload = await request.json()
    except Exception as e:
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    user_message = payload.get("message", "")
    extra_context = payload.get("extra_context", {})

    # 🔁 Merge user_input with extra_context
    full_extra = {
        **extra_context,
        "user_input": user_message,
        "raw_user_input": user_message
    }

    context = await resolve_user_context(user, extra=full_extra)
    enriched_context = enrich_context(context)
    result = await load_policy_and_resolve(agent_name, enriched_context)
    return result
