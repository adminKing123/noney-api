"""
utils/email_service.py
======================
Shared email construction + SMTP delivery (used by Fuse nodes and integrations).
"""

from __future__ import annotations

import logging
import os
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


def _smtp_runtime() -> dict:
    """
    Read SMTP settings at send time (same env keys as Bridger).

    Uses ``os.environ`` so Cloud Run / Render injected vars are always picked up,
    with ``CONFIG.SMTP`` as fallback.
    """
    cfg = CONFIG.SMTP
    host = (os.environ.get("SMTP_HOST") or cfg.HOST or "smtp.gmail.com").strip()
    port_raw = (os.environ.get("SMTP_PORT") or str(cfg.PORT or 587)).strip()
    try:
        port = int(port_raw)
    except ValueError:
        port = 587
    user = (os.environ.get("SMTP_USER") or cfg.USER or "").strip()
    password = (os.environ.get("SMTP_APP_PASSWORD") or cfg.APP_PASSWORD or "").strip()
    from_addr = (os.environ.get("SMTP_FROM") or cfg.FROM or user).strip()
    use_tls_raw = (os.environ.get("SMTP_USE_TLS") or ("true" if cfg.USE_TLS else "false")).strip()
    use_tls = use_tls_raw.lower() in ("1", "true", "yes")
    return {
        "host": host,
        "port": port,
        "user": user,
        "password": password,
        "from_addr": from_addr,
        "use_tls": use_tls,
    }


def is_smtp_configured() -> bool:
    smtp = _smtp_runtime()
    return bool(smtp["host"] and smtp["user"] and smtp["password"])


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
    smtp = _smtp_runtime()
    message["From"] = (from_addr or smtp["from_addr"] or smtp["user"]).strip()
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
    """Send ``message`` using configured SMTP credentials (STARTTLS on 587, same as Bridger)."""
    if not is_smtp_configured():
        raise RuntimeError(
            "SMTP is not configured. Set SMTP_HOST, SMTP_USER, and SMTP_APP_PASSWORD."
        )

    smtp = _smtp_runtime()
    recipients = _all_recipients(message)
    if not recipients:
        raise ValueError("No recipients on email message.")

    from_header = (message.get("From") or smtp["user"]).strip()
    if from_header and "<" not in from_header and "@" in from_header:
        from_header = f"Comet AI <{from_header}>"
    message["From"] = from_header

    try:
        with smtplib.SMTP(smtp["host"], smtp["port"], timeout=30) as server:
            server.ehlo()
            if smtp["use_tls"]:
                server.starttls()
                server.ehlo()
            server.login(smtp["user"], smtp["password"])
            server.sendmail(smtp["user"], recipients, message.as_string())
        logger.info("[email] sent to %s subject=%r", recipients, message.get("Subject"))
    except smtplib.SMTPAuthenticationError as exc:
        logger.error("[email] SMTP authentication failed (check SMTP_USER / SMTP_APP_PASSWORD)")
        raise RuntimeError("SMTP authentication failed. Check SMTP_USER and SMTP_APP_PASSWORD.") from exc
    except smtplib.SMTPException as exc:
        logger.exception("[email] SMTP send failed")
        raise RuntimeError(f"SMTP send failed: {exc}") from exc
    except OSError as exc:
        logger.exception("[email] network error connecting to %s:%s", smtp["host"], smtp["port"])
        raise RuntimeError(f"SMTP connection failed ({smtp['host']}:{smtp['port']}): {exc}") from exc


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
