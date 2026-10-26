"""
utils/email_service.py
----------------------
Email delivery via the external Email Service HTTP API.
"""

import logging
from email.message import EmailMessage

import requests

from config import CONFIG

logger = logging.getLogger(__name__)

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


def is_email_service_configured() -> bool:
    host = CONFIG.EMAIL_SERVICE.HOST
    api_key = CONFIG.EMAIL_SERVICE.API_KEY
    return bool(host and api_key)


def send_email(
    to_email: str,
    subject: str,
    body: str,
    *,
    send_as_html: bool = False,
) -> bool:
    """
    Send an email via the Email Service API.

    Returns True on success, False on validation, auth, or transport failure.
    """
    if not is_email_service_configured():
        logger.error("Email service is not configured (EMAIL_SERVICE_HOST / EMAIL_SERVICE_API_KEY).")
        return False

    base = CONFIG.EMAIL_SERVICE.HOST.rstrip("/")
    url = f"{base}/api/send-email"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {CONFIG.EMAIL_SERVICE.API_KEY}",
    }
    payload = {
        "to": to_email,
        "subject": subject,
        "body": body,
        "send_as_html": send_as_html,
        "from_name": CONFIG.EMAIL_SERVICE.FROM_NAME,
    }

    try:
        response = requests.post(url, headers=headers, json=payload, timeout=60)
        if response.status_code == 200:
            logger.info("Email sent to %s — subject: %s", to_email, subject)
            return True
        logger.error(
            "Email service error sending to %s (status=%s): %s",
            to_email,
            response.status_code,
            response.text,
        )
    except requests.RequestException as exc:
        logger.error("Network error sending email to %s: %s", to_email, exc)

    return False


def send_fuse_workflow_email(
    to_email: str,
    subject: str,
    body: str,
    *,
    content_subtype: str = "text/plain",
) -> dict:
    """
    Send workflow email via the Email Service API.

    Raises ``RuntimeError`` when send returns False (Fuse node errors).
    """
    send_as_html = content_subtype == "text/html"
    ok = send_email(to_email, subject, body, send_as_html=send_as_html)
    if not ok:
        raise RuntimeError(
            "Email send failed. Check server logs and EMAIL_SERVICE_HOST / EMAIL_SERVICE_API_KEY."
        )

    from_name = CONFIG.EMAIL_SERVICE.FROM_NAME
    return {
        "success": True,
        "to": to_email,
        "from": from_name,
        "subject": subject,
    }


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
    """Build ``EmailMessage`` for Gmail API (Send Gmail node — not app email service)."""
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
    message["From"] = (from_addr or "").strip()

    if cc and cc.strip():
        message["Cc"] = cc.strip()
    if bcc and bcc.strip():
        message["Bcc"] = bcc.strip()
    return message
