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
    
    reporter and await reporter.step("🧠 Preparing prompt")

    prompt = render_prompt_template("guess_model", context=data)

    reporter and await reporter.step("🛰️ Sending images to Vision LLM")

    llm_response = await call_llm_vision(
        prompt=prompt,
        image_urls=image_urls,
        metadata={"llm_model": "gpt-4o"},
        reporter=reporter
    )

    reporter and await reporter.step("📤 Parsing LLM response")

    raw_content = llm_response["choices"][0]["message"]["content"]
    match = re.search(r"```json\s*(\{.*?\})\s*```", raw_content, re.DOTALL)
    json_str = match.group(1) if match else raw_content.strip()

    try:
        return json.loads(json_str)
    except json.JSONDecodeError as e:
        print("⚠️ JSON decode error:", e)
        return {}
