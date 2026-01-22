import asyncio
import datetime
from typing import Optional
from uuid import UUID

from pytune_llm.task_reporting.reporter import TaskReporter
from pytune_data.piano_identification_session import (
    get_identification_session,
    update_identification_session
)
from pytune_llm.llm_vision import label_images_from_urls
from app.services.sanitizers import sanitize_labels
from datetime import datetime, timezone


async def label_images_from_session(
    session_id: UUID,
    reporter: Optional[TaskReporter] = None
) -> tuple[dict, list[dict]]:

    session = await get_identification_session(session_id)
    if not session or not session.image_urls:
        raise ValueError(f"No images found for session_id={session_id}")


    # 🧠 Prépare image_data (avec métadonnées si dispo)
    if session.photo_metadata:
        image_data = [
            {
                "url": url,
                "filename": meta.get("filename", f"photo_{i+1}.jpg")
            }
            for i, (url, meta) in enumerate(zip(session.image_urls, session.photo_metadata))
        ]
    else:
        image_data = [
            {
                "url": url,
                "filename": url.split("/")[-1]
            }
            for url in session.image_urls
        ]

    # ⚡️ Parallélise chaque appel LLM pour chaque image
    async def label_one(img: dict) -> dict:
        return await label_images_from_urls([img])  # ⬅️ garde bien comme liste

    raw_labels_nested = await asyncio.gather(*(label_one(img) for img in image_data))
    raw_labels = [lbl[0] for lbl in raw_labels_nested]  # chaque appel retourne une liste avec un seul élément

    cleaned_labels = [sanitize_labels(label) for label in raw_labels]

    metadata = {
        "prompt_version": "labeling-v1",
        "pipeline_version": "2025-07",
        "labeling_completed": True,
        "labeling_timestamp": datetime.now(timezone.utc).isoformat(),
        "num_images": len(cleaned_labels),
        "has_serial_number_count": sum(1 for lbl in cleaned_labels if lbl.get("has_serial_number"))
    }

    return metadata, cleaned_labels
