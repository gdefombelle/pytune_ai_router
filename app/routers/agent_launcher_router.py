# app/routers/agent_launcher_router.py

from fastapi import APIRouter, Depends, Request
from app.core.policy_loader import load_policy_and_resolve
from pytune_auth_common.models.schema import UserOut
from pytune_auth_common.services.auth_checks import get_current_user
from app.core.context_resolver import resolve_user_context
from app.models.policy_model import AgentResponse



router = APIRouter(prefix="/ai/agents", tags=["AI Agents"])

@router.post("/{agent_name}/start")
async def start_agent(
    agent_name: str,
    request: Request,
    user: UserOut = Depends(get_current_user)
):
    extra_context = await request.json() if request.method == "POST" else {}
    full_context = await resolve_user_context(user.id, extra=extra_context)
    return await load_policy_and_resolve(agent_name, full_context)


@router.post("/{agent_name}/evaluate")
async def evaluate_agent(agent_name: str, user_input: dict, user: UserOut = Depends(...)):
    context = await resolve_user_context(user.id)
    context.update(user_input)  # fusion dynamique
    return await load_policy_and_resolve(agent_name, context)
