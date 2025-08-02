import asyncio
import json
import re
from typing import Optional

from pytune_data.user_data_service import get_user_context
from pytune_data.piano_identification_session import update_identification_session
from pytune_llm.llm_connector import call_llm
from pytune_llm.task_reporting.reporter import TaskReporter
from app.core.prompt_builder import render_prompt_template


async def trigger_music_source_enrichment(
    piano_data: dict,
    sheet_music: dict | None,
    user_id: int,
    session_id: int,
    reporter: Optional[TaskReporter] = None
):
    if not sheet_music:
        if reporter:
            await reporter.log("No sheet music detected — skipping enrichment.")
        return

    # 1. Get user profile (level, style, etc.)
    user_context = await get_user_context(user_id)
    if not user_context:
        if reporter:
            await reporter.log(f"User profile not found for user_id={user_id}")
        return

    # 2. Clean minimal piano data
    piano_fp = {
        "brand": piano_data.get("brand"),
        "model": piano_data.get("model"),
        "category": piano_data.get("category"),
        "type": piano_data.get("type"),
        "size_cm": piano_data.get("size_cm"),
    }
    
    reporter and await reporter.log(f"[DEBUG] piano_fp: {piano_fp}")

    # 3. Build prompt
    prompt = render_prompt_template(
        "music_source_finder",
        {
            "piano": piano_fp,  # 🔁 nom aligné avec le template
            "user_profile": user_context,
            "sheet_music_list": [sheet_music],  # ou plusieurs s’il y en a plusieurs
        }
    )

    if reporter:
        await reporter.step("🎵 Fetching music source links (IMSLP, Spotify…)")

    # 4. Call LLM
    llm_response = await call_llm(
        prompt=prompt,
        context={},
        metadata={"llm_model": "gpt-4o"},
        reporter=reporter,
    )

    raw_content = llm_response

    # 5. Extract JSON block
    match = re.search(r"```json\s*(.*?)\s*```", raw_content, re.DOTALL)
    json_str = match.group(1).strip() if match else raw_content.strip()

    try:
        data = json.loads(json_str)
    except Exception as e:
        if reporter:
            await reporter.log(f"Failed to parse music source JSON: {e}")
        return

    # 6. Store in DB
    await update_identification_session(session_id, music_sources=data)

    if reporter:
        await reporter.log("🎼 Music sources stored successfully.")
