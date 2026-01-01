import re
import json
from pathlib import Path
from functools import lru_cache

from app.core.paths import POLICY_DIR
from simple_logger import get_logger, SimpleLogger

logger: SimpleLogger = get_logger()

_T_PATTERN = re.compile(r"""\$t\(['"]([^'"]+)['"]\)""")

# 🔒 évite de logger 50 fois la même clé
_MISSING_KEYS = set()


# @lru_cache(maxsize=64)
def _load_catalog(agent_name: str, lang: str) -> dict:
    base = POLICY_DIR / agent_name / "i18n" / f"{lang}.json"
    fallback = POLICY_DIR / agent_name / "i18n" / "en.json"

    path = base if base.exists() else fallback
    if not path.exists():
        return {}

    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def resolve_i18n_deep(obj, *, agent_name: str, lang: str):
    """
    Replaces all $t('key') recursively in dict / list / str.
    Logs missing keys once per (agent, lang, key).
    """

    catalog = _load_catalog(agent_name, lang or "en")

    if isinstance(obj, dict):
        return {
            k: resolve_i18n_deep(v, agent_name=agent_name, lang=lang)
            for k, v in obj.items()
        }

    if isinstance(obj, list):
        return [
            resolve_i18n_deep(v, agent_name=agent_name, lang=lang)
            for v in obj
        ]

    if isinstance(obj, str):

        def repl(match):
            key = match.group(1)

            if key in catalog:
                return catalog[key]

            # 🔔 LOG ICI (une seule fois)
            fingerprint = (agent_name, lang, key)
            if fingerprint not in _MISSING_KEYS:
                _MISSING_KEYS.add(fingerprint)
                logger.warning(
                    f"[i18n] Missing key '{key}' "
                    f"(agent={agent_name}, lang={lang})"
                )

            return f"[missing:{key}]"

        return _T_PATTERN.sub(repl, obj)

    return obj