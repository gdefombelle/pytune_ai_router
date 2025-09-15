from typing import Dict, Any
from copy import deepcopy

def merge_first_piano_data(
    base: Dict[str, Any],
    update: Dict[str, Any],
    skip_empty: bool = True
) -> Dict[str, Any]:
    """
    Fusionne deux blocs de données `first_piano`, en conservant les valeurs utiles de `base`,
    sauf si `update` fournit une valeur non vide.
    Les booléens explicites comme `model_dont_know: true` sont toujours conservés,
    même si `skip_empty` est activé.
    """
    merged = deepcopy(base)

    for key, value in update.items():
        if skip_empty:
            if value in [None, "", 0] and not isinstance(value, bool):
                continue
        merged[key] = value

    return merged
