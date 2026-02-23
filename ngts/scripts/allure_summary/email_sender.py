"""
Email Sending Module for Allure Summary Tool.

This module handles sending HTML emails via SMTP.
"""

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import List

from ngts.scripts.allure_summary.config import MAIL_SERVER, MAIL_PORT, SENDER_EMAIL, SENDER_NAME
from ngts.scripts.allure_summary.models import EmailConfig
from ngts.scripts.allure_summary.logger import get_logger

logger = get_logger()


def send_email(
    recipients: List[str],
    subject: str,
    html_body: str,
    dry_run: bool = False
) -> bool:
    """
    Send an HTML email to the specified recipients.

    Args:
        recipients: List of email addresses
        subject: Email subject line
        html_body: HTML content for the email body
        dry_run: If True, don't actually send (just log)

    Returns:
        True if email was sent successfully, False otherwise
    """
    if not recipients:
        logger.error("No recipients specified")
        return False

    logger.info(f"Preparing email to: {', '.join(recipients)}")
    logger.debug(f"Subject: {subject}")
    logger.debug(f"HTML body size: {len(html_body)} bytes")

    if dry_run:
        logger.info("[DRY RUN] Email would be sent to:")
        for recipient in recipients:
            logger.info(f"  - {recipient}")
        logger.info(f"[DRY RUN] Subject: {subject}")
        logger.info("[DRY RUN] Email content preview (first 500 chars):")
        logger.info(html_body[:500] + "..." if len(html_body) > 500 else html_body)
        return True

    try:
        # Create message
        msg = MIMEMultipart("alternative")
        msg["Subject"] = subject
        msg["From"] = f"{SENDER_NAME} <{SENDER_EMAIL}>"
        msg["To"] = ", ".join(recipients)

        # Add plain text fallback
        plain_text = "Please view this email in an HTML-capable client."
        msg.attach(MIMEText(plain_text, "plain"))

        # Add HTML body
        msg.attach(MIMEText(html_body, "html"))

        logger.debug(f"Connecting to SMTP server: {MAIL_SERVER}:{MAIL_PORT}")

        # Send email
        with smtplib.SMTP(MAIL_SERVER, MAIL_PORT, timeout=30) as server:
            logger.debug("Connected to SMTP server")
            server.sendmail(SENDER_EMAIL, recipients, msg.as_string())
            logger.debug("Email sent via SMTP")

        logger.info(f"✅ Email sent successfully to: {', '.join(recipients)}")
        return True

    except smtplib.SMTPAuthenticationError as e:
        logger.error(f"[SMTP AUTH ERROR] Authentication failed: {e}")
        return False
    except smtplib.SMTPRecipientsRefused as e:
        logger.error(f"[SMTP ERROR] Recipients refused: {e}")
        return False
    except smtplib.SMTPException as e:
        logger.error(f"[SMTP ERROR] Failed to send email: {e}")
        return False
    except ConnectionRefusedError:
        logger.error(f"[CONNECTION ERROR] Cannot connect to SMTP server: {MAIL_SERVER}:{MAIL_PORT}")
        return False
    except TimeoutError:
        logger.error(f"[TIMEOUT ERROR] SMTP server connection timed out")
        return False
    except Exception as e:
        logger.error(f"[UNEXPECTED ERROR] {type(e).__name__}: {e}")
        return False


def send_with_config(config: EmailConfig, html_body: str) -> bool:
    """
    Send email using an EmailConfig object.

    Args:
        config: EmailConfig with recipients and subject
        html_body: HTML content for the email body

    Returns:
        True if email was sent successfully, False otherwise
    """
    return send_email(
        recipients=config.recipients,
        subject=config.subject,
        html_body=html_body,
        dry_run=config.dry_run
    )
