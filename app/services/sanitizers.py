

from PIL.TiffImagePlugin import IFDRational
def sanitize_labels(raw: dict) -> dict:
    """
    Nettoie et normalise les champs retournés par label_image_from_url
    pour garantir une structure cohérente et exploitable.
    """

    # Valeurs autorisées
    VALID_ANGLES = {"front", "side", "top", "angled", "unknown"}
    VALID_VIEW_TYPES = {"keyboard", "full", "logo", "internal", "other"}
    VALID_LIGHTING = {"well-lit", "dark", "blurry", "partial"}

    # Sanitize chaque champ
    angle = raw.get("angle", "").lower()
    view_type = raw.get("view_type", "").lower()
    lighting = raw.get("lighting", "").lower()
    content = raw.get("content", [])
    notes = raw.get("notes", "")

    return {
        "angle": angle if angle in VALID_ANGLES else "unknown",
        "view_type": view_type if view_type in VALID_VIEW_TYPES else "other",
        "lighting": lighting if lighting in VALID_LIGHTING else "unknown",
        "content": content if isinstance(content, list) else [],
        "notes": str(notes)[:300]  # limite défensive
    }


def sanitize_exif(obj):
    if isinstance(obj, IFDRational):
        return float(obj)
    elif isinstance(obj, dict):
        return {k: sanitize_exif(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [sanitize_exif(v) for v in obj]
    else:
        return obj
