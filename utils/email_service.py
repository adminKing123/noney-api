"""
utils/email_service.py
======================
Shared email construction + SMTP delivery (used by Fuse nodes and integrations).
"""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage
from config import CONFIG

logger = logging.getLogger(__name__)

# Appended to every Get Notified (Email) node message (server-side only).
GET_NOTIFIED_EMAIL_SIGNATURE_PLAIN = (
    "\n\n---\n"
    "Comet AI\n"
    "Automated notification from your workflow."
)

GET_NOTIFIED_EMAIL_SIGNATURE_HTML = (
    '<div style="margin-top:24px;padding-top:16px;border-top:1px solid #e5e7eb;'
    'color:#6b7280;font-size:13px;line-height:1.5;font-family:-apple-system,BlinkMacSystemFont,'
    '"Segoe UI",Roboto,sans-serif;">'
    '<strong style="color:#111827;font-size:14px;">Comet AI</strong><br/>'
    '<span style="font-size:12px;">Automated notification from your workflow.</span>'
    "</div>"
)


def apply_get_notified_email_signature(body: str, content_subtype: str) -> str:
    """Append the fixed Comet AI footer; callers must not allow user overrides."""
    text = (body or "").rstrip()
    if content_subtype == "text/html":
        return f"{text}{GET_NOTIFIED_EMAIL_SIGNATURE_HTML}"
    return f"{text}{GET_NOTIFIED_EMAIL_SIGNATURE_PLAIN}"


def is_smtp_configured() -> bool:
    smtp = CONFIG.SMTP
    return bool(smtp.HOST and smtp.USER and smtp.APP_PASSWORD)


def build_email_message(
    *,
    to: str,
    subject: str,
    body: str,
    from_addr: str | None = None,
    cc: str | None = None,
    bcc: str | None = None,
    content_subtype: str = "plain",
) -> EmailMessage:
    """Build a standard ``EmailMessage`` (plain or html body)."""
    if not to.strip():
        raise ValueError("Missing recipient email address.")
    if not subject.strip():
        raise ValueError("Missing email subject.")
    if body is None or body == "":
        raise ValueError("Missing email body.")

    subtype = "html" if content_subtype == "text/html" else "plain"
    message = EmailMessage()
    message.set_content(body, subtype=subtype)
    message["To"] = to.strip()
    message["Subject"] = subject.strip()
    message["From"] = (from_addr or CONFIG.SMTP.FROM or CONFIG.SMTP.USER).strip()
    if cc and cc.strip():
        message["Cc"] = cc.strip()
    if bcc and bcc.strip():
        message["Bcc"] = bcc.strip()
    return message


def _all_recipients(message: EmailMessage) -> list[str]:
    recipients: list[str] = []
    for header in ("To", "Cc", "Bcc"):
        raw = message.get(header)
        if not raw:
            continue
        recipients.extend(addr.strip() for addr in raw.split(",") if addr.strip())
    return recipients


def send_email_via_smtp(message: EmailMessage) -> None:
    """Send ``message`` using configured SMTP credentials."""
    if not is_smtp_configured():
        raise RuntimeError(
            "SMTP is not configured. Set SMTP_HOST, SMTP_USER, and SMTP_APP_PASSWORD."
        )

    smtp = CONFIG.SMTP
    recipients = _all_recipients(message)
    if not recipients:
        raise ValueError("No recipients on email message.")

    try:
        with smtplib.SMTP(smtp.HOST, smtp.PORT, timeout=30) as server:
            if smtp.USE_TLS:
                server.starttls()
            server.login(smtp.USER, smtp.APP_PASSWORD)
            server.send_message(message, from_addr=message["From"], to_addrs=recipients)
    except smtplib.SMTPException as exc:
        logger.exception("[email] SMTP send failed")
        raise RuntimeError(f"SMTP send failed: {exc}") from exc


def send_email(
    *,
    to: str,
    subject: str,
    body: str,
    from_addr: str | None = None,
    cc: str | None = None,
    bcc: str | None = None,
    content_subtype: str = "plain",
) -> dict:
    """
    Build and send one email. Returns metadata for workflow node output.
    """
    message = build_email_message(
        to=to,
        subject=subject,
        body=body,
        from_addr=from_addr,
        cc=cc,
        bcc=bcc,
        content_subtype=content_subtype,
    )
    send_email_via_smtp(message)
    return {
        "success": True,
        "to": message["To"],
        "from": message["From"],
        "subject": message["Subject"],
    }
