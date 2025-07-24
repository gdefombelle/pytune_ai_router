import asyncio
from typing import Any, Dict
from uuid import UUID
from fastapi import APIRouter, Depends, HTTPException, Request, Body
from pytune_chat.store import get_conversation_history
from app.core.policy_loader import load_policy_and_resolve, load_yaml, start_policy
from app.core.context_resolver import resolve_user_context
from app.core.context_enrichment import enrich_context
from pytune_auth_common.models.schema import UserOut
from pytune_auth_common.services.auth_checks import get_current_user
from app.models.policy_model import AgentResponse
from pytune_chat.store import append_message

# ✅ Handlers spécialisés
from app.handlers.piano_agent_handler import (
    piano_agent_handler,
    piano_agent_start_handler,
    save_piano_handler
)
from app.utils.context_helpers import prepare_enriched_context
from app.utils.piano_merge import merge_first_piano_data
from app.utils.dontknow_utils import humanize_dont_know_list, inject_dont_know_message_if_needed

router = APIRouter(prefix="/ai/agents", tags=["AI Agents"])

@router.post("/{agent_name}/start", response_model=AgentResponse)
async def start_agent(
    agent_name: str,
    extra_context: dict = Body(..., embed=True),
    user: UserOut = Depends(get_current_user),
):
    policy = load_yaml(agent_name)
    use_memory = policy.get("metadata", {}).get("memory") is True

    # 🧠 Crée une conversation si mémoire activée
    conversation_id = None
    if use_memory:
        from pytune_chat.store import create_conversation
        conv = await create_conversation(user.id, topic=agent_name)
        conversation_id = str(conv.id)

    # 🔧 Résout et enrichit le contexte utilisateur
    full_context = await resolve_user_context(user, extra=extra_context)
    enriched_context = enrich_context(full_context)

    # Injecte le conversation_id si applicable
    if conversation_id:
        enriched_context["conversation_id"] = conversation_id

    # ✅ Appelle le bloc `start` ou fallback vers policy loader
    response = await start_policy(agent_name, enriched_context)

    # 🏷️ Injecte le titre du YAML si présent
    title = policy.get("metadata", {}).get("title")
    if title:
        response.meta = {
            **response.meta,
            "title": title
        }

    # 🧠 Historise le message assistant s’il y en a un
    if conversation_id and response.message:
        from pytune_chat.store import append_message
        try:
            await append_message(UUID(conversation_id), "assistant", response.message)
        except Exception as e:
            print(f"⚠️ Failed to log initial assistant message: {e}")

    # 🔁 Retourne conversation_id dans la meta si présent
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

    # 🔧 Construit le contexte de base (utilisateur + extra)
    base_context = {
        **extra_context,
        "user_input": "",
        "raw_user_input": "",
        "conversation_id": conversation_id,
    }

    context = await resolve_user_context(user, extra=base_context)
    enriched_context = enrich_context(context)

    # ✅ Récupère le snapshot AVANT de l'utiliser
    snapshot = extra_context.get("agent_form_snapshot", {})

    # ✅ Fusionne tous les blocs de snapshot (agnostique)
    for key, value in snapshot.items():
        old = enriched_context.get(key, {})
        if not isinstance(old, dict):
            print(f"⚠️ Skipping merge: enriched_context[{key}] is not a dict (got {type(old).__name__})")
            continue
        if not isinstance(value, dict):
            print(f"⚠️ Skipping merge: snapshot[{key}] is not a dict (got {type(value).__name__})")
            continue

        enriched_context[key] = {
            **old,
            **value,
        }

    # 🔁 Injecte les dont_know_flags dans first_piano (pour matcher le YAML)
    if "dont_know_flags" in snapshot and "first_piano" in enriched_context:
        for k, v in snapshot["dont_know_flags"].items():
            if k not in enriched_context["first_piano"]:
                enriched_context["first_piano"][k] = v

    # 💾 Enregistre le piano si confirmé mais pas encore sauvegardé
    first_piano = snapshot.get("first_piano") or enriched_context.get("first_piano", {})
    save_response = None
    if first_piano.get("confirmed") and not first_piano.get("saved"):
        email = enriched_context.get("email")
        if email:
            save_response = await save_piano_handler(context=enriched_context, email=email)
            enriched_context["first_piano"] = {
                **enriched_context.get("first_piano", {}),
                **save_response.context_update.get("first_piano", {}),
            }

    # 🤖 Exécution de la policy
    response = await load_policy_and_resolve(agent_name, enriched_context)

    # ✅ Si save_response a un message/action → fusionne dans la réponse principale
    if save_response:
        if save_response.message:
            response.message = (response.message or "") + f"\n\n{save_response.message}"
        if save_response.actions:
            response.actions = save_response.actions
        if save_response.context_update:
            response.context_update = {
                **(response.context_update or {}),
                **save_response.context_update
            }

    # 🧠 Historisation mémoire
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

@router.post("/{agent_name}/flags", response_model=AgentResponse)
async def submit_flags(
    agent_name: str,
    request: Request,
    user: UserOut = Depends(get_current_user),
):
    try:
        payload = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON")

    extra_context = payload.get("extra_context", {})
    snapshot = extra_context.get("agent_form_snapshot", {})
    flags = snapshot.get("dont_know_flags", {})

    conversation_id = extra_context.get("conversation_id")
    readable = humanize_dont_know_list([k for k, v in flags.items() if v])

    msg = f"✅ Got it — {readable}, we can skip it for now." if readable else ""

    if conversation_id and msg:
        try:
            uuid_ = UUID(conversation_id)
            await append_message(uuid_, "assistant", msg)
        except Exception as e:
            print(f"⚠️ Failed to append assistant message from /flags: {e}")

    return AgentResponse(
        message=msg,
        context_update={
            "agent_form_snapshot": {
                "dont_know_flags": {**flags}
            }
        }
    )

