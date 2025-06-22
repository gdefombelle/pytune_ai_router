from typing import Optional, List, Tuple
from pytune_data.serial_number_data_service import get_serial_number_info
from pytune_llm.llm_client import call_llm_vision, ask_llm
import re

async def resolve_age(
    manufacturer_id: int,
    serial_number: Optional[str],
    brand_name: Optional[str] = None,
    image_urls: Optional[List[str]] = None
) -> Tuple[Optional[int], int, str]:
    # Vérifie dans la base interne si le numéro est renseigné et non "Unknown", etc.
    if manufacturer_id and serial_number and serial_number.lower() not in {"unknown", "not specified", "n/a", "none"}:
        info = await get_serial_number_info(manufacturer_id, serial_number)
        if info and info.get("year"):
            return info["year"], 100, "Found in internal serial number database."

    # Sinon, estimation LLM textuelle
    if serial_number and serial_number.lower() not in {"unknown", "not specified", "n/a", "none"} and brand_name:
        prompt = f"What is the approximate year of manufacture for a {brand_name} piano with serial number {serial_number}?"
        try:
            llm_answer = await ask_llm(user_input=prompt, context={}, prompt_template="$user_input")
            match = re.search(r"\b(18|19|20)\d{2}\b", llm_answer)
            if match:
                return int(match.group(0)), 85, "Estimated via LLM web lookup (text-based)."
        except Exception as e:
            print(f"[LLM Age Lookup] Failed: {e}")

    # Sinon, analyse image
    if image_urls and brand_name:
        vision_prompt = f"Based on these images and the brand {brand_name}, estimate the year the piano was manufactured. Respond with a single 4-digit year."
        try:
            vision_response = await call_llm_vision(prompt=vision_prompt, image_urls=image_urls)
            content = vision_response["choices"][0]["message"]["content"]
            match = re.search(r"\b(18|19|20)\d{2}\b", content)
            if match:
                return int(match.group(0)), 70, "Estimated via LLM vision analysis."
        except Exception as e:
            print(f"[Vision Age Estimation] Failed: {e}")

    return None, 0, "No reliable information available."
