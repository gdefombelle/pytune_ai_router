from typing import List
from pytune_llm.llm_client import call_llm_vision
from app.core.prompt_builder import render_prompt_template

async def guess_model_from_images(data: dict, image_urls: List[str]) -> dict:
    prompt = render_prompt_template("guess_model", **data)

    llm_response = await call_llm_vision(
        prompt=prompt,
        image_urls=image_urls,
        metadata={"llm_model": "gpt-4o"}
    )

    return llm_response
