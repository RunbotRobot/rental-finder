"""Sends an outreach email through your own Gmail account.

Gmail SMTP with an App Password, not a transactional-email API: replies
land in your real inbox the normal way, and the landlord sees your actual
address rather than a third-party sending domain. Requires 2-Step
Verification enabled on the account and an App Password generated for it
(README has the exact steps) -- a normal account password will not work
here and should never be used for this.

Every call is a single, real, irreversible send. This module doesn't
decide who to email -- main.py's gate does that -- it only does the
sending and reports whether it worked.
"""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage

from .config import Settings

logger = logging.getLogger(__name__)

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465


def send(to_address: str, subject: str, body: str, settings: Settings) -> tuple[bool, str]:
    """(success, message). Never raises -- a failed send is reported, not fatal
    to the run, since one bad address shouldn't stop the rest."""
    if not settings.gmail_address or not settings.gmail_app_password:
        return False, "Gmail credentials not configured"

    message = EmailMessage()
    message["From"] = settings.gmail_address
    message["To"] = to_address
    message["Subject"] = subject
    message.set_content(body)

    try:
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=settings.request_timeout_seconds) as smtp:
            smtp.login(settings.gmail_address, settings.gmail_app_password)
            smtp.send_message(message)
        return True, "sent"
    except smtplib.SMTPException as exc:
        logger.warning("Failed to send to %s: %s", to_address, exc)
        return False, f"SMTP error: {exc}"
    except OSError as exc:
        logger.warning("Failed to send to %s: %s", to_address, exc)
        return False, f"connection error: {exc}"
