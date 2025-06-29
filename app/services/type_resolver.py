# /utils/piano_extract.py

from typing import Optional

PIANO_TYPE_RANGES = {
    "upright": [
        ("Spinet", 91, 102),
        ("Console", 103, 109),
        ("Studio", 110, 123),
        ("Full upright", 124, 150),
    ],
    "grand": [
        ("Baby Grand", 130, 155),
        ("Medium", 156, 170),
        ("Parlor", 171, 190),
        ("Music room", 191, 220),
        ("Concert", 221, 307),
    ]
}

def resolve_type(category: Optional[str], size_cm: Optional[float]) -> Optional[str]:
    """
    Déduit le type de piano à partir de la catégorie ('upright' ou 'grand') et de la taille en cm.
    Renvoie None si non déterminable.
    """
    if not category or not size_cm:
        return None

    for type_name, min_cm, max_cm in PIANO_TYPE_RANGES.get(category.lower(), []):
        if min_cm <= size_cm <= max_cm:
            return type_name

    return None
