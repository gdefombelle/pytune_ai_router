from jinja2 import Environment, FileSystemLoader
from app.core.paths import EMAIL_TEMPLATES_DIR

email_templates = Environment(
    loader=FileSystemLoader(str(EMAIL_TEMPLATES_DIR)),
    autoescape=True
)
