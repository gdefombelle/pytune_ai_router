from typing import List, Optional
from pytune_llm.llm_client import call_llm_vision
from pytune_llm.task_reporting.reporter import TaskReporter
from app.core.prompt_builder import render_prompt_template
import re
import json

async def guess_model_from_images(
        data: dict, 
        image_urls: List[str],
        reporter: Optional[TaskReporter]) -> dict:

    prompt = render_prompt_template("guess_model", context=data)

    llm_response = await call_llm_vision(
        prompt=prompt,
        image_urls=image_urls,
        reporter=reporter
    )

    raw_content = llm_response.get("raw_text", "")
    match = re.search(r"```json\s*(\{.*?\})\s*```", raw_content, re.DOTALL)
    json_str = match.group(1) if match else raw_content.strip()

    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        print("⚠️ JSON decode error:", e)
        print("Raw content was:\n", raw_content)
        return {}
