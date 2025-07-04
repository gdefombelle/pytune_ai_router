from uuid import UUID
from pytune_auth_common.models.schema import UserOut
from pytune_chat.store import get_conversation_history

from app.core.context_resolver import resolve_user_context
from app.core.context_enrichment import enrich_context


async def prepare_enriched_context(
    user: UserOut,
    agent_name: str,
    message: str,
    extra_context: dict,
) -> dict:
    convo_id = extra_context.get("conversation_id")
    full_extra = {
        **extra_context,
        "user_input": message,
        "raw_user_input": message,
        "conversation_id": convo_id,
    }    # 🧠 Ajout last_prompt à l’extra context
    # 🧠 Ajout last_prompt à l’extra context
    if convo_id:
        try:
            uuid_ = UUID(convo_id)
            history = await get_conversation_history(uuid_)
            last_prompt = next((m["content"] for m in reversed(history) if m["role"] == "assistant"), None)
            if last_prompt:
                full_extra["last_prompt"] = last_prompt
        except Exception as e:
            print(f"⚠️ Failed to get last_prompt: {e}")




    context = await resolve_user_context(user, extra=full_extra)
    context = enrich_context(context)
    return context
