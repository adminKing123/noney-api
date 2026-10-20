"""
utils/email_service.py
----------------------
SMTP email delivery using Python's built-in smtplib over STARTTLS (port 587).

Mirrors Bridger: app/services/email_service.py
"""

import html
import logging
import smtplib
from email.message import EmailMessage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

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
    smtp_user = CONFIG.SMTP.USER
    smtp_password = CONFIG.SMTP.APP_PASSWORD
    return bool(smtp_user and smtp_password)


def send_email(
    to_email: str,
    subject: str,
    html_body: str,
    text_body: str | None = None,
) -> bool:
    """
    Send an email via SMTP with STARTTLS.

    Args:
        to_email:  Recipient email address.
        subject:   Email subject line.
        html_body: HTML version of the body.
        text_body: Plain-text fallback (optional).

    Returns:
        True on success, False on any SMTP / connection failure.
    """
    smtp_host: str = CONFIG.SMTP.HOST
    smtp_port: int = CONFIG.SMTP.PORT
    smtp_user: str = CONFIG.SMTP.USER
    smtp_password: str = CONFIG.SMTP.APP_PASSWORD

    if not smtp_user or not smtp_password:
        logger.error("SMTP credentials are not configured.")
        return False

    # Build multipart/alternative message
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"Comet AI <{smtp_user}>"
    msg["To"] = to_email

    if text_body:
        msg.attach(MIMEText(text_body, "plain", "utf-8"))
    msg.attach(MIMEText(html_body, "html", "utf-8"))

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=10) as server:
            server.ehlo()
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.sendmail(smtp_user, to_email, msg.as_string())
        logger.info("Email sent to %s — subject: %s", to_email, subject)
        return True

    except smtplib.SMTPAuthenticationError:
        logger.error("SMTP authentication failed. Check SMTP_USER and SMTP_APP_PASSWORD.")
    except smtplib.SMTPException as exc:
        logger.error("SMTP error sending to %s: %s", to_email, exc)
    except OSError as exc:
        logger.error("Network error sending email to %s: %s", to_email, exc)

    return False


def send_fuse_smtp_email(
    to_email: str,
    subject: str,
    body: str,
    *,
    content_subtype: str = "text/plain",
) -> dict:
    """
    Send workflow email using ``send_email`` (Bridger transport).

    Raises ``RuntimeError`` when SMTP send returns False (Fuse node errors).
    """
    if content_subtype == "text/html":
        html_body = body
        text_body = None
    else:
        text_body = body
        html_body = f"<pre style=\"font-family: sans-serif; white-space: pre-wrap;\">{html.escape(body)}</pre>"

    ok = send_email(to_email, subject, html_body, text_body)
    if not ok:
        raise RuntimeError("SMTP send failed. Check server logs and SMTP settings.")

    smtp_user = CONFIG.SMTP.USER
    return {
        "success": True,
        "to": to_email,
        "from": f"Comet AI <{smtp_user}>",
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
    """Build ``EmailMessage`` for Gmail API (Send Gmail node — not SMTP)."""
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
    message["From"] = (from_addr or CONFIG.SMTP.USER or "").strip()

    if cc and cc.strip():
        message["Cc"] = cc.strip()
    if bcc and bcc.strip():
        message["Bcc"] = bcc.strip()
    return message
