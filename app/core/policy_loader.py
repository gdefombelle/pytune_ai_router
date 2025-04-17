# core/policy_loader.py
# 👈 ← Charge et parse les YAML
import yaml
from typing import Any

def load_policy(path: str) -> list[dict[str, Any]]:
    with open(path, 'r', encoding='utf-8') as f:
        data = yaml.safe_load(f)
    return data.get("on_user_login", [])
