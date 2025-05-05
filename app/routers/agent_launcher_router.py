# app/routers/agent_launcher_router.py

from typing import Any, Dict
from fastapi import APIRouter, Depends, HTTPException, Request, Body
from app.core.policy_loader import load_policy_and_resolve
from app.core.context_resolver import resolve_user_context
from pytune_auth_common.models.schema import UserOut
from pytune_auth_common.services.auth_checks import get_current_user
from app.models.policy_model import AgentResponse

router = APIRouter(prefix="/ai/agents", tags=["AI Agents"])


@router.post("/{agent_name}/start", response_model=AgentResponse)
async def start_agent(
    agent_name: str,
    extra_context: dict = Body(default={}),
    user: UserOut = Depends(get_current_user),
):
    """
    Démarre un agent avec un éventuel contexte additionnel (ex: onboarding).
    """
    full_context = await resolve_user_context(user, extra=extra_context)
    return await load_policy_and_resolve(agent_name, full_context)


@router.post("/{agent_name}/evaluate", response_model=AgentResponse)
async def evaluate_agent(
    agent_name: str,
    user_input: dict = Body(default={}),
    user: UserOut = Depends(get_current_user),
):
    """
    Permet d'évaluer dynamiquement une policy à chaque étape d'interaction.
    """
    full_context = await resolve_user_context(user, extra=user_input)
    return await load_policy_and_resolve(agent_name, full_context)


from fastapi import Request

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
    context = await resolve_user_context(user, extra={"user_input": user_message})
    return await load_policy_and_resolve(agent_name, context)
