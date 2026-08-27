"""Email delivery for approved contracts."""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage
from pathlib import Path
from typing import Optional

from ..config import (
    EMAIL_DRY_RUN,
    EMAIL_FROM,
    EMAIL_SUBJECT_PREFIX,
    SMTP_HOST,
    SMTP_PASSWORD,
    SMTP_PORT,
    SMTP_USE_TLS,
    SMTP_USER,
)

logger = logging.getLogger(__name__)


def send_contract_email(
    *,
    to_email: str,
    subject: str,
    body: str,
    attachment_path: Optional[str | Path] = None,
    cc: Optional[list[str]] = None,
) -> dict:
    """Send the modified contract to the client.

    When EMAIL_DRY_RUN is true (default), logs the payload and returns success
    without connecting to SMTP.
    """
    if not to_email:
        return {"status": "error", "error_message": "client email is required"}

    full_subject = subject if subject.startswith(EMAIL_SUBJECT_PREFIX) else f"{EMAIL_SUBJECT_PREFIX} {subject}"
    payload = {
        "to": to_email,
        "cc": cc or [],
        "from": EMAIL_FROM,
        "subject": full_subject,
        "body": body,
        "attachment": str(attachment_path) if attachment_path else None,
        "dry_run": EMAIL_DRY_RUN,
    }

    if EMAIL_DRY_RUN:
        logger.info("EMAIL_DRY_RUN: would send %s", payload)
        return {"status": "success", "dry_run": True, **payload}

    if not SMTP_HOST:
        return {
            "status": "error",
            "error_message": "SMTP_HOST is not configured and EMAIL_DRY_RUN is false",
        }

    msg = EmailMessage()
    msg["From"] = EMAIL_FROM
    msg["To"] = to_email
    if cc:
        msg["Cc"] = ", ".join(cc)
    msg["Subject"] = full_subject
    msg.set_content(body)

    if attachment_path:
        path = Path(attachment_path)
        data = path.read_bytes()
        maintype, subtype = "application", "vnd.openxmlformats-officedocument.wordprocessingml.document"
        msg.add_attachment(data, maintype=maintype, subtype=subtype, filename=path.name)

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=30) as smtp:
        if SMTP_USE_TLS:
            smtp.starttls()
        if SMTP_USER:
            smtp.login(SMTP_USER, SMTP_PASSWORD)
        smtp.send_message(msg)

    return {"status": "success", "dry_run": False, "to": to_email, "subject": full_subject}
