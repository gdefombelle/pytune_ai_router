
from io import BytesIO
import traceback
from typing import Dict
from pytune_data.models import User
from pytune_helpers.email_helper import EmailService
from simple_logger import SimpleLogger, get_logger, logger
from core.templates import email_templates

logger = logger or SimpleLogger()
async def send_piano_summary_email(user: User, pdf_buffer: BytesIO, piano_info: Dict):
    email_service = EmailService()

    try:
        html_body = email_templates.get_template("piano_summary_email.html").render(
            user=user.first_name,
            brand=piano_info.get("brand"),
            year=piano_info.get("year_estimated"),
            model=piano_info.get("model_hypothesis", {}).get("name"),
            variant=piano_info.get("model_hypothesis", {}).get("variant"),
            description=piano_info.get("model_hypothesis", {}).get("description"),
        )

        await email_service.send_email(
            to_email=user.email,
            subject="📄 Your Piano Summary Report",
            body=html_body,
            attachments=[{
                "filename": "piano_summary.pdf",
                "content": pdf_buffer,
                "content_type": "application/pdf"
            }],
            is_html=True,
            send_background=True,
        )

    except Exception as e:
        tb = traceback.format_exc()
        await logger.acritical(
            f"Failed to send summary PDF to {user.email} - {e}\n{tb}"
        )

    email_service = EmailService()
    
    # Render the HTML body (use your existing Jinja2 template or create a new one)
    html_body = email_templates.get_template("piano_summary_email.html").render(
        user=user.first_name,
        brand=piano_info.get("brand"),
        year=piano_info.get("year_estimated"),
        model=piano_info.get("model_hypothesis", {}).get("name"),
    )

    try:
        await email_service.send_email(
            to_email=user.email,
            subject="📄 Your Piano Summary Report",
            body=html_body,
            attachments=[{
                "filename": "piano_summary.pdf",
                "content": pdf_buffer,
                "content_type": "application/pdf"
            }],
            is_html=True,
            send_background=True,
        )
    except Exception as e:
        tb = traceback.format_exc()
        await logger.acritical(f"Failed to send summary PDF to {user.email} - {e}\n{tb}")

    email_service = EmailService()
    
    # Render the HTML body (use your existing Jinja2 template or create a new one)
    html_body = email_templates.get_template("piano_summary_email.html").render(
        user=user.first_name,
        brand=piano_info.get("brand"),
        year=piano_info.get("year_estimated"),
        model=piano_info.get("model_hypothesis", {}).get("name"),
    )

    try:
        await email_service.send_email(
            to_email=user.email,
            subject="📄 Your Piano Summary Report",
            body=html_body,
            attachments=[{
                "filename": "piano_summary.pdf",
                "co
