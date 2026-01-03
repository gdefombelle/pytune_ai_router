import json
import re
from app.services.type_resolver import resolve_type
from app.utils.dontknow_utils import humanize_dont_know_list

def looks_invalid(text: str) -> bool:
    if not text or not isinstance(text, str):
        return True  # vide ou None est considéré comme invalide
    text = text.strip()
    return (
        len(text) < 2
        or len(text) > 50
        or not re.search(r"[a-zA-Z]", text)
        or re.search(r"[#@^%*_=+{}[\]<>]", text)
    )

def normalize_approximate_values(fp: dict, metadata: dict) -> None:
    """
    Normalise les champs size_cm, year_estimated, model incertains (~145, circa 1940, Chopin?)
    et ajoute des flags dans metadata.
    """

    # 🎯 Année approximative (ex: "circa 1940")
    year_raw = fp.get("year_estimated")
    if isinstance(year_raw, str):
        match = re.search(r"\b(18\d{2}|19\d{2}|20[01]\d)\b", year_raw)
        if match:
            fp["year_estimated"] = int(match.group(1))
            metadata["year_approx"] = True

    # 📏 Taille approximative (ex: "~140", "about 145")
    size_raw = fp.get("size_cm")
    if isinstance(size_raw, str):
        match = re.search(r"(\d{2,3})", size_raw)
        if match:
            size_val = int(match.group(1))
            if 40 <= size_val <= 300:
                fp["size_cm"] = size_val
                metadata["size_approx"] = True
            else:
                fp["size_cm"] = None
                metadata["size_rejected"] = True

    # ❓ Modèle incertain (ex: "Chopin?", "maybe C3")
    model = fp.get("model", "")
    if isinstance(model, str) and ("?" in model or "maybe" in model.lower()):
        fp["model"] = model.replace("?", "").replace("maybe", "").strip()
        metadata["model_uncertain"] = True

    # 🧠 Flag global
    if metadata.get("year_approx") or metadata.get("size_approx") or metadata.get("model_uncertain"):
        metadata["approximation_detected"] = True

def render_warnings(metadata: dict) -> str:
    """
    Affiche joliment les avertissements détectés dans metadata["warnings"].
    """
    warnings = metadata.get("warnings", [])
    if not warnings:
        return ""

    return "\n\n⚠️ Some values were approximate or corrected:\n" + "\n".join(f"- {w}" for w in warnings)



def extract_structured_piano_data(text: str) -> dict:
    """
    Tente de parser un message contenant potentiellement du texte suivi d’un bloc JSON.
    Valide les champs incohérents (modèle, marque, taille) et normalise les valeurs approximatives.
    """
    try:
        # 🔍 Extraire le premier bloc JSON valide s’il y a du texte autour
        match = re.search(r"{[\s\S]+}", text)
        if match:
            text = match.group(0).strip()

        data = json.loads(text)
        if not isinstance(data, dict) or "first_piano" not in data:
            return {}

        extracted = data
        fp = extracted.get("first_piano", {})
        metadata = extracted.setdefault("metadata", {})

        # 🔍 Validation du modèle
        if "model" in fp and looks_invalid(fp["model"]):
            print(f"⚠️ Invalid model rejected: {fp['model']}")
            fp["model"] = ""
            metadata["model_rejected"] = True

        # 🔍 Validation de la marque
        if "brand" in fp and looks_invalid(fp["brand"]):
            print(f"⚠️ Invalid brand rejected: {fp['brand']}")
            fp["brand"] = ""
            metadata["brand_rejected"] = True

        # 🔍 Validation de la taille numérique
        if "size_cm" in fp and isinstance(fp["size_cm"], (int, float)):
            size = fp["size_cm"]
            if size < 40 or size > 300:
                print(f"⚠️ Unrealistic size_cm rejected: {size}")
                fp["size_cm"] = None
                metadata["size_rejected"] = True

        # 🧠 Normalisation approximative : "~145", "circa 1940", "Chopin?"
        normalize_approximate_values(fp, metadata)

        return extracted

    except json.JSONDecodeError as e:
        print("❌ JSON decode error:", e)
        return {}


def make_readable_message_from_extraction(
    extracted: dict,
    brand_resolution: dict | None = None,
    user_lang: str | None = None,
) -> str:
    """
    Construit un message lisible à partir des données extraites par le LLM,
    avec explication des champs reconnus ou des réponses implicites.
    """
    lang = (user_lang or "en").lower()
    is_fr = lang.startswith("fr")

    fp = extracted.get("first_piano", {}) or {}
    metadata = extracted.get("metadata", {}) or {}
    confidences = extracted.get("confidences", {}) or {}
    corrections = []

    acknowledged = metadata.get("acknowledged")
    if acknowledged:
        flags = acknowledged if isinstance(acknowledged, list) else [acknowledged]
        readable = humanize_dont_know_list(flags)
        if readable:
            return (
                f"✅ C’est noté — {readable}, on peut ignorer pour le moment."
                if is_fr
                else f"✅ Got it — {readable}, we can skip it for now."
            )

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
        prefix = "~" if metadata.get("size_approx") else ""
        corrections.append(f'Size: {prefix}{fp["size_cm"]} cm')

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

        intro = (
            "🎹 J’ai extrait et mis à jour les informations suivantes à partir de votre message :"
            if is_fr
            else "🎹 I’ve extracted and updated the following information from your message:"
        )

        closing = (
            "Dites-moi si quelque chose doit être ajusté ou corrigé."
            if is_fr
            else "Let me know if anything needs to be adjusted or corrected!"
        )

        return (
            intro + "\n"
            + "\n".join(f"- {line}" for line in corrections)
            + "\n\n" + closing
        )


    return (
        "J’ai analysé votre message, mais je n’ai pas encore pu extraire d’informations structurées."
        if is_fr
        else "I’ve analyzed your message but couldn’t extract any structured information yet."
    )
