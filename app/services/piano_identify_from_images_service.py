import asyncio
from datetime import datetime
import json

from pytune_llm.task_reporting.reporter import TaskReporter
from unidecode import unidecode
from pytune_data.db import init
from pytune_data.piano_data_service import search_manufacturer, search_manufacturer_full
from typing import List, Optional, Tuple
from openai import AsyncOpenAI
import re
from pytune_data.serial_number_data_service import get_serial_number_info, get_serial_year, get_manufacturer_name
from pytune_configuration.sync_config_singleton import config, SimpleConfig
from pytune_data.models import PianoSerialCache
from pytune_llm.llm_client import call_llm_vision
from pytune_data.user_data_service import get_user_context
from app.services.image_metadata_utils import build_image_context_description
from .brand_resolver_vision import resolve_manufacturer_vision
from .age_resolver_vision import resolve_age_vision
from app.core.prompt_builder import render_prompt_template


async def identify_piano_from_images(
    manufacturer_id: Optional[int],
    image_urls: List[str],
    image_metadata: Optional[list[dict]] = None,
    reporter: Optional[TaskReporter] = None
) -> dict:
    try:
        manufacturer_name = (
            await get_manufacturer_name(manufacturer_id)
            if manufacturer_id and manufacturer_id != 0 else None
        )
        optical_context = build_image_context_description(image_metadata or [])
        photos = [
        {
            "filename": meta.get("filename", f"photo_{i+1}.jpg"),
            "url": meta.get("minio_url")
        }
        for i, meta in enumerate(image_metadata or [])
]
        prompt = render_prompt_template("identify_piano", {
            "manufacturer_name": manufacturer_name or "",
            "optical_context": optical_context,
            "photos": photos 
        })
        

        llm_response = await call_llm_vision(
            prompt=prompt,
            image_urls=image_urls,
            metadata={"llm_model": "gpt-4o"},
            reporter=reporter
        )

        await asyncio.sleep(0.01)

        raw_content = llm_response["choices"][0]["message"]["content"]
        match = re.search(r"```json\s*(\{.*?\})\s*```", raw_content, re.DOTALL)
        json_str = match.group(1) if match else raw_content.strip()
        data = json.loads(json_str)
 
        # Champs principaux
        brand = data.get("brand")
        category = data.get("category")
        piano_type = data.get("type")
        serial_number = data.get("serial_number")
        size_cm = data.get("size_cm")
        nb_notes = data.get("nb_notes")
        confidences = data.get("confidences", {})
        brand_conf = confidences.get("brand", 0)
        category_conf = confidences.get("category", 0)

        estimated_value_eur = data.get("estimated_value_eur")
        value_confidence = data.get("value_confidence", 0)

        # Bloc partition si présent
        music_title = data.get("music_title")
        music_level = data.get("music_level")
        music_style = data.get("music_style")
        sheet_music = None
        if music_title or music_level or music_style:
            sheet_music = {
                "title": music_title,
                "level": music_level,
                "style": music_style
            }

        # Préparation future : ambiance / décor / objets visibles
        scene_description = data.get("scene_description")  # attendu plus tard

        # Résolution du fabricant
        resolved_id, resolved_brand_name, metadata = await resolve_manufacturer_vision(
            brand_from_llm=brand,
            brand_conf=brand_conf
        )

        if not resolved_id:
            return {
                "status": "manufacturer_error",
                "reason": metadata.get("reason") if metadata else "unresolved",
                "llm_brand": brand,
                "matches": await search_manufacturer_full(brand, email=None),
                "extra": {
                    "sheet_music": sheet_music,
                    "scene_description": scene_description
                }
            }

        # Estimation de l’âge
        age, age_confidence, age_method = await resolve_age_vision(
            manufacturer_id=resolved_id,
            serial_number=serial_number,
            brand_name=resolved_brand_name,
            image_urls=image_urls,
            reporter=reporter
        )

        return {
            "status": "ok",
            "brand": resolved_brand_name,
            "manufacturer_id": resolved_id,
            "category": category,
            "type": piano_type,
            "serial_number": serial_number,
            "size_cm": size_cm,
            "nb_notes": nb_notes,
            "age": age,
            "age_confidence": age_confidence,
            "age_method": age_method,
            "confidence": int((brand_conf + category_conf) / 2),
            "metadata": metadata or {},
            "extra": {
                "sheet_music": sheet_music,
                "scene_description": scene_description,
                "estimated_value_eur": estimated_value_eur,
                "value_confidence": value_confidence,
                "photos": photos,
            },
            

        }

    except Exception as e:
        print(f"[❌ identify_piano_from_images failed] {e}")
        return {
            "status": "error",
            "message": str(e)
        }
