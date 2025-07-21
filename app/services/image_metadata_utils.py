def build_image_context_description(image_metadata: list[dict]) -> str:
    """
    Génère une description textuelle concise de l'origine optique des photos
    à injecter dans un prompt LLM pour aider à estimer les dimensions du piano.
    """
    if not image_metadata:
        return ""

    lines = []

    for meta in image_metadata:
        optics = meta.get("optics", {})
        if not optics:
            continue

        # Nom du device
        make = optics.get("make") or ""
        model = optics.get("model") or "unknown device"
        camera = f"{make} {model}".strip()

        # Focale
        focal_35 = optics.get("focal_length_35mm")
        focal_native = optics.get("focal_length_mm")
        focal_str = (
            f"{focal_35}mm" if focal_35
            else f"{round(focal_native, 1)}mm" if focal_native
            else "?"
        )

        # Résolution
        size = meta.get("size_original", {})
        res_width = size.get("width")
        res_height = size.get("height")
        resolution = f"{res_width}x{res_height}" if res_width and res_height else None

        # Assemble la ligne
        parts = [
            f"Photo from {camera}",
            f"focal length: {focal_str}" if focal_str != "?" else None,
            f"resolution: {resolution}" if resolution else None
        ]

        line = " | ".join(p for p in parts if p)
        if line:
            lines.append(line)

    return "\n".join(lines)
