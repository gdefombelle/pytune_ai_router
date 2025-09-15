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
from pytune_llm.task_reporting.reporter import TaskReporter

# ✅ Handlers spécialisés
from app.handlers.piano_agent_handler import (
    piano_agent_handler,
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
    # 🧠 Initialize the task reporter (4 steps total here, adjust if needed)
    reporter = TaskReporter(agent_name, auto_progress=True)

    # Step 1: Load agent policy
    await reporter.step("📥 Loading policy")
    policy = load_yaml(agent_name)
    use_memory = policy.get("metadata", {}).get("memory") is True

    # Step 2: Create memory-based conversation if required
    conversation_id = None
    await reporter.step("🧠 Creating memory" if use_memory else "🧠 Skipping memory")
    if use_memory:
        from pytune_chat.store import create_conversation
        conv = await create_conversation(user.id, topic=agent_name)
        conversation_id = str(conv.id)

    # Step 3: Resolve full context (user + environment + extra)
    await reporter.step("📥 Resolving context")
    full_context = await resolve_user_context(user, extra=extra_context)
    enriched_context = enrich_context(full_context)

    if conversation_id:
        enriched_context["conversation_id"] = conversation_id

    # Step 4: Run the `start` block from policy
    await reporter.step("🚀 Launching agent")
    response = await start_policy(agent_name, enriched_context, reporter=reporter)

    # Optionally inject agent title (if defined in YAML)
    title = policy.get("metadata", {}).get("title")
    if title:
        response.meta = {
            **response.meta,
            "title": title
        }

    # Store the assistant’s first message in memory if available
    if conversation_id and response.message:
        from pytune_chat.store import append_message
        try:
            await append_message(UUID(conversation_id), "assistant", response.message)
        except Exception as e:
            print(f"⚠️ Failed to log assistant message: {e}")

    # Always return conversation ID if created
    if conversation_id:
        response.meta = {
            **response.meta,
            "conversation_id": conversation_id
        }

    # ✅ Mark task as done
    await reporter.done()

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
    
    reporter = TaskReporter(agent_name, auto_progress=True)
    await reporter.step("📦 Resolving context")
    extra_context = payload.get("extra_context", {})
    conversation_id = extra_context.get("conversation_id")

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

    # 🤖 Exécution de la policy
    await reporter.step("📦 Resolving policy")
    response = await load_policy_and_resolve(agent_name, enriched_context, reporter=reporter)

    await reporter.step("✅ Finalizing")
    # 🧠 Historisation mémoire
    if conversation_id and response.message:
        try:
            uuid_ = UUID(conversation_id)
            await append_message(uuid_, "assistant", response.message)
        except Exception as e:
            print(f"⚠️ Failed to append assistant message from /evaluate: {e}")
    await reporter.done()
    return response


@router.post("/{agent_name}/message", response_model=AgentResponse)
async def agent_message(
    agent_name: str,
    request: Request,
    user: UserOut = Depends(get_current_user),
):
    reporter = TaskReporter(agent_name, auto_progress=True)

    payload = await request.json()
    message = payload.get("message", "")
    extra_context = payload.get("extra_context", {})

    await reporter.step("📥 Preparing context")
    context = await prepare_enriched_context(user, agent_name, message, extra_context)

    if agent_name == "piano_agent":
        await reporter.step("🎹 Piano agent handler")
        ret = await piano_agent_handler(agent_name, message, context, reporter=reporter)
        await reporter.done()
        return ret

    await reporter.step("🧠 Running policy")
    response = await load_policy_and_resolve(agent_name, context, reporter=reporter)
    await reporter.done()
    return response

@router.post("/{agent_name}/flags", response_model=AgentResponse)
async def submit_flags(
    agent_name: str,
    request: Request,
    user: UserOut = Depends(get_current_user),
):
    reporter = TaskReporter(agent_name, total_steps=1, auto_progress=True)
    await reporter.step("🏁 Handling flags")

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

    await reporter.done()
    return AgentResponse(
        message=msg,
        context_update={
            "agent_form_snapshot": {
                "dont_know_flags": {**flags}
            }
        }
    )

