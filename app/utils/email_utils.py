"""
Email utility functions
"""
import logging
from typing import Optional, List
from app.config import settings

logger = logging.getLogger(__name__)


async def send_email(
    to_email: str,
    subject: str,
    body: str,
    is_html: bool = False,
    from_email: Optional[str] = None,
) -> bool:
    """
    Send an email
    
    This is a placeholder implementation. In production, you would use:
    - SMTP (built-in Python smtplib)
    - SendGrid API
    - AWS SES
    - Mailgun API
    - etc.
    """
    try:
        if not settings.SMTP_SERVER:
            logger.warning("Email sending is not configured. Skipping email.")
            return True  # Return True to avoid breaking flows in development

        # Placeholder for actual email sending logic
        logger.info(f"Would send email to: {to_email}")
        logger.info(f"Subject: {subject}")
        logger.info(f"Body preview: {body[:100]}...")

        # Example using SMTP (uncomment and configure):
        # import smtplib
        # from email.mime.text import MIMEText
        # from email.mime.multipart import MIMEMultipart
        
        # msg = MIMEMultipart()
        # msg['From'] = from_email or settings.EMAIL_FROM
        # msg['To'] = to_email
        # msg['Subject'] = subject
        
        # if is_html:
        #     msg.attach(MIMEText(body, 'html'))
        # else:
        #     msg.attach(MIMEText(body, 'plain'))
        
        # with smtplib.SMTP(settings.SMTP_SERVER, settings.SMTP_PORT) as server:
        #     server.starttls()
        #     server.login(settings.SMTP_USERNAME, settings.SMTP_PASSWORD)
        #     server.send_message(msg)

        return True
    except Exception as e:
        logger.error(f"Error sending email to {to_email}: {e}")
        return False


async def send_bulk_email(
    to_emails: List[str],
    subject: str,
    body: str,
    is_html: bool = False,
    from_email: Optional[str] = None,
) -> int:
    """Send email to multiple recipients"""
    success_count = 0
    
    for email in to_emails:
        try:
            success = await send_email(
                to_email=email,
                subject=subject,
                body=body,
                is_html=is_html,
                from_email=from_email,
            )
            if success:
                success_count += 1
        except Exception as e:
            logger.error(f"Error sending email to {email}: {e}")
    
    return success_count


def render_email_template(template_name: str, context: dict) -> str:
    """Render email template with context"""
    # This is a simplified version. In production, use Jinja2 or similar.
    templates = {
        "welcome": """
        Welcome to Social Media API!
        
        Hello {name},
        
        Thank you for joining our community!
        
        Best regards,
        The Team
        """,
        "password_reset": """
        Password Reset Request
        
        Hello {name},
        
        You requested a password reset. Click the link below:
        {reset_link}
        
        This link will expire in 24 hours.
        
        If you didn't request this, please ignore this email.
        
        Best regards,
        The Team
        """,
        "verification": """
        Email Verification
        
        Hello {name},
        
        Please verify your email by clicking the link below:
        {verification_link}
        
        Best regards,
        The Team
        """,
    }
    
    template = templates.get(template_name, "")
    
    # Simple template rendering
    for key, value in context.items():
        placeholder = "{" + key + "}"
        template = template.replace(placeholder, str(value))
    
    return template