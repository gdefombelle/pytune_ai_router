from copy import deepcopy
from typing import Dict, Any


def merge_first_piano_data(
    base: Dict[str, Any],
    update: Dict[str, Any],
    skip_empty: bool = True
) -> Dict[str, Any]:
    """
    Fusionne deux blocs de données `first_piano`, en conservant les valeurs utiles de `base`,
    sauf si `update` fournit une valeur non vide.
    """
    merged = deepcopy(base)

    for key, value in update.items():
        if skip_empty:
            if value in [None, "", 0]:
                continue
        merged[key] = value

    return merged
