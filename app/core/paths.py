from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
PROMPT_DIR = STATIC_DIR / "agents" / "prompts"
POLICY_DIR = STATIC_DIR / "agents" / "templates"
EMAIL_TEMPLATES_DIR = STATIC_DIR / "email_templates"
PAGE_TEMPLATES_DIR = STATIC_DIR / "pages_templates"
