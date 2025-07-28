from typing import Optional, Tuple
from pytune_llm.task_reporting.reporter import TaskReporter
from unidecode import unidecode

from pytune_data.db import init
from pytune_data.models import Manufacturer
from pytune_data.piano_data_service import search_manufacturer_full
from pytune_data.schemas import ManufacturerCreate, ManufacturerInDB

SIMILARITY_THRESHOLD = 0.9
AMBIGUITY_THRESHOLD = 0.5
LLM_CONFIDENCE_ACCEPT = 80


async def create_manufacturer_from_llm_vision(brand_name: str) -> ManufacturerInDB:
    await init()
    new_entry = await Manufacturer.create(
        company=brand_name,
        originated_by="llm"
    )
    return {
        "id": new_entry.id,
        "company": new_entry.company
    }


async def resolve_manufacturer_vision(
    brand_from_llm: Optional[str],
    brand_conf: Optional[int] = 0,
    reporter: Optional[TaskReporter]=None
) -> Tuple[Optional[int], Optional[str], Optional[dict]]:
    """
    Résout un nom de marque détecté par LLM (image), avec fallback si inconnu.

    Retourne : (manufacturer_id, resolved_name, metadata)
    """
    if not brand_from_llm:
        return None, None, {"reason": "missing_brand"}

    matches = await search_manufacturer_full(brand_from_llm, email=None)

    # Cas 1 — Match trouvé
    if matches:
        top = matches[0]
        return top["id"], top["company"], {"matched_from_input": brand_from_llm}

    # Cas 2 — Aucun match trouvé
    if brand_conf >= LLM_CONFIDENCE_ACCEPT:
        created = await create_manufacturer_from_llm_vision(brand_from_llm)
        return created["id"], created["company"], {"created_by_llm": True}

    return None, brand_from_llm, {"reason": "not_found"}
  
