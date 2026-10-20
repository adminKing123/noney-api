"""
utils/email_service.py
======================
SMTP delivery — same pattern as Bridger (smtplib + STARTTLS on port 587).

Bridger reference: app/services/email_service.py
"""

from __future__ import annotations

import logging
import smtplib
from email.message import EmailMessage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from config import CONFIG

logger = logging.getLogger(__name__)

_SMTP_TIMEOUT = 10
_FROM_DISPLAY = "Comet AI"

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


def _smtp_config() -> tuple[str, int, str, str]:
    """Same env keys as Bridger: SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_APP_PASSWORD."""
    cfg = CONFIG.SMTP
    host = cfg.HOST or "smtp.gmail.com"
    port = int(cfg.PORT or 587)
    user = (cfg.USER or "").strip()
    password = (cfg.APP_PASSWORD or "").strip()
    return host, port, user, password


def is_smtp_configured() -> bool:
    _host, _port, user, password = _smtp_config()
    return bool(user and password)


def _deliver_smtp(msg: MIMEMultipart, to_addrs: list[str]) -> None:
    """
    Send a MIME message over SMTP (Bridger-compatible).

    Raises ``RuntimeError`` on failure so Fuse nodes can surface errors.
    """
    smtp_host, smtp_port, smtp_user, smtp_password = _smtp_config()

    if not smtp_user or not smtp_password:
        raise RuntimeError(
            "SMTP is not configured. Set SMTP_USER and SMTP_APP_PASSWORD."
        )

    if not to_addrs:
        raise ValueError("No recipients for email.")

    try:
        with smtplib.SMTP(smtp_host, smtp_port, timeout=_SMTP_TIMEOUT) as server:
            server.ehlo()
            server.starttls()
            server.login(smtp_user, smtp_password)
            server.sendmail(smtp_user, to_addrs, msg.as_string())
        logger.info("Email sent to %s — subject: %s", to_addrs, msg.get("Subject"))
    except smtplib.SMTPAuthenticationError as exc:
        logger.error(
            "SMTP authentication failed. Check SMTP_USER and SMTP_APP_PASSWORD."
        )
        raise RuntimeError(
            "SMTP authentication failed. Check SMTP_USER and SMTP_APP_PASSWORD."
        ) from exc
    except smtplib.SMTPException as exc:
        logger.error("SMTP error sending to %s: %s", to_addrs, exc)
        raise RuntimeError(f"SMTP send failed: {exc}") from exc
    except OSError as exc:
        logger.error("Network error sending email to %s: %s", to_addrs, exc)
        raise RuntimeError(
            f"SMTP connection failed ({smtp_host}:{smtp_port}): {exc}"
        ) from exc


def _build_smtp_mime(
    *,
    to_email: str,
    subject: str,
    body: str,
    content_subtype: str = "plain",
    from_display: str = _FROM_DISPLAY,
) -> MIMEMultipart:
    """Build multipart/alternative MIME like Bridger (plain and/or html)."""
    _, _, smtp_user, _ = _smtp_config()

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject.strip()
    msg["From"] = f"{from_display} <{smtp_user}>"
    msg["To"] = to_email.strip()

    if content_subtype == "text/html":
        msg.attach(MIMEText(body, "html", "utf-8"))
    else:
        msg.attach(MIMEText(body, "plain", "utf-8"))

    return msg


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
    Build and send one email via SMTP. Returns metadata for workflow node output.

    ``from_addr`` / ``cc`` / ``bcc`` are accepted for API compatibility; SMTP
    From uses the configured SMTP user (same envelope behaviour as Bridger).
    """
    if not to.strip():
        raise ValueError("Missing recipient email address.")
    if not subject.strip():
        raise ValueError("Missing email subject.")
    if body is None or body == "":
        raise ValueError("Missing email body.")

    subtype = "html" if content_subtype == "text/html" else "plain"
    msg = _build_smtp_mime(
        to_email=to,
        subject=subject,
        body=body,
        content_subtype=subtype,
    )

    recipients = [to.strip()]
    if cc and cc.strip():
        msg["Cc"] = cc.strip()
        recipients.extend(a.strip() for a in cc.split(",") if a.strip())
    if bcc and bcc.strip():
        msg["Bcc"] = bcc.strip()
        recipients.extend(a.strip() for a in bcc.split(",") if a.strip())

    _deliver_smtp(msg, recipients)

    return {
        "success": True,
        "to": msg["To"],
        "from": msg["From"],
        "subject": msg["Subject"],
    }


# ── Gmail API (OAuth) — not sent via SMTP ─────────────────────────────────────


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
    """Build ``EmailMessage`` for Gmail API (Send Gmail node)."""
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

    _, _, smtp_user, _ = _smtp_config()
    from_email = (from_addr or smtp_user).strip()
    message["From"] = from_email

    if cc and cc.strip():
        message["Cc"] = cc.strip()
    if bcc and bcc.strip():
        message["Bcc"] = bcc.strip()
    return message
