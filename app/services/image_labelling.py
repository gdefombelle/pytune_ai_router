from uuid import UUID
from pytune_data.piano_identification_session import (
    get_identification_session,
    update_identification_session
)
from pytune_llm.llm_vision import label_images_from_urls
from app.services.sanitizers import sanitize_labels

async def label_images_from_session(session_id: UUID) -> list[dict]:
    session = await get_identification_session(session_id)
    if not session or not session.image_urls:
        raise ValueError(f"No images found for session_id={session_id}")

    # ⚙️ Prépare image_data selon disponibilité metadata
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

    photo_labels = await label_images_from_urls(image_data)
    cleaned_labels = [sanitize_labels(label) for label in photo_labels]
    #await update_identification_session(session_id, photo_labels=cleaned_labels)

    return cleaned_labels
