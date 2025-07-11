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
