from uuid import UUID
from pytune_data.piano_identification_session import (
    get_identification_session,
    update_identification_session
)
from pytune_llm.llm_vision import label_images_from_urls
from services.sanitizers import sanitize_labels

async def label_images_from_session(session_id: UUID) -> list[dict]:
    """
    Récupère une session, labellise ses images via LLM vision, et met à jour les photo_labels.
    """
    session = await get_identification_session(session_id)
    if not session or not session.image_urls:
        raise ValueError(f"No images found for session_id={session_id}")

    photo_labels = await label_images_from_urls(session.image_urls)
    cleaned_labels = [sanitize_labels(label) for label in photo_labels]
    # Mise à jour du champ photo_labels
    await update_identification_session(session_id, photo_labels=cleaned_labels)

    return photo_labels
