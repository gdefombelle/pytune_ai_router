def humanize_dont_know_list(flags: list[str]) -> str:
    """
    Converts a list of flags like ['model_dont_know', 'serial_dont_know'] 
    into a human-readable phrase like: 
    "you don’t know the model and the serial number"
    """
    label_map = {
        "model_dont_know": "the model",
        "serial_dont_know": "the serial number",
        "size_dont_know": "the size"
    }

    parts = [label_map.get(f, f) for f in flags if f in label_map]

    if not parts:
        return ""

    if len(parts) == 1:
        return f"you don’t know {parts[0]}"
    elif len(parts) == 2:
        return f"you don’t know {parts[0]} and {parts[1]}"
    else:
        return f"you don’t know {', '.join(parts[:-1])}, and {parts[-1]}"


def clean_dont_know_flags(first_piano: dict, metadata: dict) -> tuple[dict, dict]:
    """
    Supprime les flags *_dont_know incohérents si les valeurs correspondantes sont renseignées.
    Nettoie aussi metadata['acknowledged'] si présent.
    Retourne le tuple (first_piano, metadata) nettoyé.
    """
    updated_fp = first_piano.copy()
    updated_meta = metadata.copy() if metadata else {}

    for field, value_key in {
        "model_dont_know": "model",
        "serial_dont_know": "serial_number",
        "size_dont_know": "size_cm"
    }.items():
        if updated_fp.get(field) is True:
            value = updated_fp.get(value_key)
            if value not in [None, "", 0]:
                updated_fp[field] = False

    # Nettoyage acknowledged
    if "acknowledged" in updated_meta and isinstance(updated_meta["acknowledged"], list):
        updated_meta["acknowledged"] = [
            flag for flag in updated_meta["acknowledged"]
            if updated_fp.get(flag) is True
        ]

    return updated_fp, updated_meta

def inject_dont_know_message_if_needed(response, enriched_context: dict):
    """
    Injecte un message synthétique si *_dont_know est présent dans le contexte
    et que le message LLM ne le mentionne pas déjà.
    """
    message = response.message or ""
    lower_msg = message.lower()

    if any(kw in lower_msg for kw in ["skip", "you don’t know", "you don't know"]):
        return  # le message est déjà pertinent, on ne touche pas

    fp = enriched_context.get("first_piano", {}) or {}
    flags = []
    if fp.get("model_dont_know"):
        flags.append("model_dont_know")
    if fp.get("serial_dont_know"):
        flags.append("serial_dont_know")
    if fp.get("size_dont_know") or fp.get("size_cm") == 0:
        flags.append("size_dont_know")

    if flags:
        from .dontknow_utils import humanize_dont_know_list
        readable = humanize_dont_know_list(flags)
        if readable:
            response.message = f"✅ Got it — {readable}, we can skip it for now."

