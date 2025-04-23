from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from app.core.policy_loader import load_policy_and_resolve
from pytune_data.models import UserContext
import asyncio

router = APIRouter(prefix="/ai/chat")

@router.post("/message")
async def chat_handler():
    """
    Réponse immédiate (non streamée) du Welcome Agent avec UserContext simulé.
    """
    user_context = UserContext(
        firstname="Gabriel TEST",
        form_completed=False,
        pianos=[],
        last_diagnosis_exists=False,
        tuning_session_exists=False,
        language="en",
    )

    agent_response = await load_policy_and_resolve("welcome_agent", user_context)
    return agent_response.model_dump()  # ✅ au lieu de .dict()

@router.get("/stream")
async def chat_stream(request: Request):
    """
    Stream de test : envoie une réponse caractère par caractère.
    """
    async def event_generator():
        message = "🎹 Hello! I’m your PyTune assistant. Let’s get started..."
        for char in message:
            if await request.is_disconnected():
                break
            yield f"data: {char}\n\n"
            await asyncio.sleep(0.025)
        yield "data: [END]\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
