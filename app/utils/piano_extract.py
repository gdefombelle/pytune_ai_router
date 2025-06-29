import json
from app.services.type_resolver import resolve_type
def extract_structured_piano_data(text: str) -> dict:
    """
    Tente de parser `text` comme JSON et d'extraire le bloc `first_piano` s’il existe.
    """
    try:
        data = json.loads(text)
        if isinstance(data, dict) and "first_piano" in data:
            return data["first_piano"]
    except json.JSONDecodeError as e:
        print("❌ JSON decode error:", e)

    return {}

def make_readable_message_from_extraction(
    extracted: dict,
    brand_resolution: dict | None = None
) -> str:
    """
    Construit un message lisible à partir des données extraites par le LLM, avec explication des inférences.
    """
    fp = extracted.get("first_piano", {}) or {}
    corrections = []

    # ✅ Marque (corrigée si applicable)
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
        corrections.append(f'Notes: {fp["nb_notes"]}')

    # 🎹 Catégorie
    if fp.get("category"):
        corrections.append(f'Category: {fp["category"]}')

    # 🧩 Type : inféré si nécessaire
    piano_type = fp.get("type")
    inferred_type = None
    if not piano_type and fp.get("category") and fp.get("size_cm"):
        inferred_type = resolve_type(fp["category"], fp["size_cm"])
        if inferred_type:
            corrections.append(f'Type: {inferred_type} (inferred from size and category)')
    elif piano_type:
        corrections.append(f'Type: {piano_type}')

    # 💬 Finalisation
    if corrections:
        return (
            "🎹 I’ve extracted and updated the following information from your message:\n"
            + "\n".join(f"- {line}" for line in corrections)
            + "\n\nLet me know if anything needs to be adjusted or corrected!"
        )
    else:
        return "I’ve analyzed your message but couldn’t extract any structured information yet."
