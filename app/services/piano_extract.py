import json
from app.services.type_resolver import resolve_type
from app.utils.dontknow_utils import humanize_dont_know_list


def extract_structured_piano_data(text: str) -> dict:
    """
    Tente de parser `text` comme JSON et retourne le dictionnaire complet s’il est bien formé.
    """
    try:
        data = json.loads(text)
        if isinstance(data, dict) and "first_piano" in data:
            return data  # 🔁 On retourne TOUT (first_piano, confidences, metadata, ...)
    except json.JSONDecodeError as e:
        print("❌ JSON decode error:", e)

    return {}

def make_readable_message_from_extraction(
    extracted: dict,
    brand_resolution: dict | None = None
) -> str:
    """
    Construit un message lisible à partir des données extraites par le LLM,
    avec explication des champs reconnus ou des réponses implicites.
    """
    fp = extracted.get("first_piano", {}) or {}
    metadata = extracted.get("metadata", {}) or {}
    confidences = extracted.get("confidences", {}) or {}
    corrections = []

    acknowledged = metadata.get("acknowledged")
    if acknowledged:
        flags = acknowledged if isinstance(acknowledged, list) else [acknowledged]
        readable = humanize_dont_know_list(flags)
        if readable:
            return f"✅ Got it — {readable}, we can skip it for now."

    CATEGORY_MAP = {1: "grand", 2: "upright", "1": "grand", "2": "upright"}

    # ✅ Marque
    if brand_resolution:
        matched = brand_resolution.get("matched_name")
        original = fp.get("brand")
        if matched and matched != original:
            corrections.append(f'Brand: **{matched}** (corrected from "{original}")')
        elif matched:
            corrections.append(f'Brand: **{matched}**')
        else:
            corrections.append(f'Brand: **{fp.get("brand")}**')
    elif fp.get("brand"):
        corrections.append(f'Brand: **{fp["brand"]}**')

    # 🆔 Modèle
    if fp.get("model"):
        corrections.append(f'Model: {fp["model"]}')

    # 🔢 Numéro de série
    if fp.get("serial_number"):
        corrections.append(f'Serial number: {fp["serial_number"]}')

    # 🧠 Année estimée
    if fp.get("year_estimated"):
        source = fp.get("year_estimated_source") or "inferred"
        corrections.append(f'Estimated year: {fp["year_estimated"]} ({source})')

    # 📏 Dimensions
    if fp.get("size_cm"):
        corrections.append(f'Size: {fp["size_cm"]} cm')

    # 🎵 Nombre de notes
    if fp.get("nb_notes"):
        confidence = confidences.get("nb_notes", 0)
        if confidence == 0:
            corrections.append(f'Notes: {fp["nb_notes"]} (default)')
        else:
            corrections.append(f'Notes: {fp["nb_notes"]}')

    # 🎹 Catégorie (avec conversion numérique éventuelle)
    cat = fp.get("category")
    if cat:
        readable_cat = CATEGORY_MAP.get(cat, cat)
        corrections.append(f'Category: {str(readable_cat).capitalize()}')

    # 🧩 Type
    if fp.get("type"):
        corrections.append(f'Type: {fp["type"]}')
    elif cat and fp.get("size_cm"):
        inferred = resolve_type(CATEGORY_MAP.get(cat, cat), fp["size_cm"])
        if inferred:
            corrections.append(f'Type: {inferred} (inferred from size and category)')

    # 💬 Finalisation
    if corrections:
        return (
            "🎹 I’ve extracted and updated the following information from your message:\n"
            + "\n".join(f"- {line}" for line in corrections)
            + "\n\nLet me know if anything needs to be adjusted or corrected!"
        )

    return "I’ve analyzed your message but couldn’t extract any structured information yet."
