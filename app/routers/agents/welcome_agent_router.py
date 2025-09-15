from fastapi import APIRouter, Depends
from app.core.context_resolver import resolve_user_context
from app.core.policy_loader import load_policy_and_resolve
from app.models.policy_model import AgentResponse
from pytune_auth_common.models.schema import UserOut
from pytune_auth_common.services.auth_checks import get_current_user

router = APIRouter(prefix="/ai/agents/welcome")

@router.post("/start", response_model=AgentResponse)
async def start_welcome_agent(user: UserOut = Depends(get_current_user)):
    """
    Starts the Welcome Agent conversation based on the user's context.
    """
    # 🔥 On récupère tout le contexte utilisateur à partir de son ID
    user_context = await resolve_user_context(user.id)

    # 🔥 On charge la policy welcome_agent et on génère la réponse
    agent_response = await load_policy_and_resolve("welcome_agent", user_context)

    return agent_response
