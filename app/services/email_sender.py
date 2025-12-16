
from io import BytesIO
import traceback
from typing import Dict
from pytune_data.models import User
from pytune_helpers_messaging import EmailService
from simple_logger.logger import SimpleLogger, get_logger
from app.core.templates import email_templates
import traceback

logger: SimpleLogger =get_logger()

async def send_piano_summary_email(user: User, pdf_url:str, piano_info: Dict):
    email_service = EmailService()

    try:

        # 📧 Génére le corps HTML avec le lien
        html_body = email_templates.get_template("piano_summary_email.html").render(
            user=user.first_name,
            brand=piano_info.get("brand"),
            year=piano_info.get("year_estimated"),
            model=piano_info.get("model_hypothesis", {}).get("name"),
            variant=piano_info.get("model_hypothesis", {}).get("variant"),
            description=piano_info.get("model_hypothesis", {}).get("description"),
            pdf_url=pdf_url  # 👈 injecté dans le template
        )

        await email_service.send_email(
            to_email=user.email,
            subject="📄 Your Piano Summary Report",
            body=html_body,
            is_html=True,
            send_background=True
        )

    except Exception as e:
        tb = traceback.format_exc()
        await logger.acritical(
            f"Failed to send summary PDF to {user.email} - {e}\n{tb}"
        )
   