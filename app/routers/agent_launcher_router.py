# app/routers/agent_launcher_router.py

from fastapi import APIRouter, Depends
from app.core.policy_loader import load_policy_and_resolve
from pytune_auth_common.models.schema import UserOut
from pytune_auth_common.services.auth_checks import get_current_user
from app.core.context_resolver import resolve_user_context
from app.models.policy_model import AgentResponse



router = APIRouter(prefix="/ai/agents", tags=["AI Agents"])

@router.post("/{agent_name}/start", response_model=AgentResponse)
async def start_agent(agent_name: str, user: UserOut = Depends(get_current_user)):
    """
    Starts any agent by name using the dynamic policy resolver.
    """
    user_context = await resolve_user_context(user.id)
    response = await load_policy_and_resolve(agent_name, user_context)
    return response
