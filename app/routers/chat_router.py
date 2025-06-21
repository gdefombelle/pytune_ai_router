from fastapi import APIRouter, Body, HTTPException, Request
from fastapi.responses import StreamingResponse
from pytune_chat.models import Role
from pytune_chat.store import append_message, get_conversation_history
from app.core.policy_loader import load_policy_and_resolve
from pytune_data.models import UserContext
import asyncio

router = APIRouter(prefix="/ai/chat")

@router.post("/message")
async def chat_handler(
    conversation_id: str = Body(...),
    user_input: str = Body(...),
    language: str = Body("en"),
):
    try:
        # À terme : récupérer dynamiquement UserContext depuis session ou auth
        user_context = UserContext(
            firstname="",
            form_completed=False,
            pianos=[],
            last_diagnosis_exists=False,
            tuning_session_exists=False,
            language=language,
        )

        # Sauvegarde du message utilisateur
        await append_message(conversation_id, Role.USER, user_input)

        # Historique (si nécessaire dans prompt de l'agent)
        history = await get_conversation_history(conversation_id)

        # Appel de l'agent
        agent_response = await load_policy_and_resolve("welcome_agent", user_context)

        # Sauvegarde de la réponse de l’agent
        await append_message(conversation_id, Role.ASSISTANT, agent_response.message)

        return agent_response.model_dump()

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

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
