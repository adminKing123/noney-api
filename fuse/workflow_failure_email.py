"""
fuse/workflow_failure_email.py
==============================
Best-effort email to the workflow owner when a run fails.
"""

from __future__ import annotations

import html
import logging
from datetime import datetime
from typing import Any

from config import CONFIG
from db import db
from utils.email_service import (
    apply_get_notified_email_signature,
    is_email_service_configured,
    send_email,
)

logger = logging.getLogger(__name__)

_BODY = 'font-family: Arial, Helvetica, sans-serif; color: #333333; line-height: 1.6; font-size: 14px;'
_TABLE = "border-collapse: collapse; width: 100%; max-width: 700px; font-size: 14px;"
_TH = "border: 1px solid #dddddd; padding: 10px; text-align: left; background-color: #f5f5f5;"
_TD = "border: 1px solid #dddddd; padding: 10px;"
_LINK = 'color: #0563C1; text-decoration: none;'
_EM_DASH = "—"


def _run_detail_url(run_id: str) -> str | None:
    base = (CONFIG.FRONTEND_URL or "").strip().rstrip("/")
    if not base:
        return None
    return f"{base}/fuse/runs/{run_id}"


def _format_when(iso_value: str | None) -> str:
    if not iso_value:
        return _EM_DASH
    text = iso_value.strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        return datetime.fromisoformat(text).strftime("%b %d, %Y at %I:%M %p")
    except ValueError:
        return iso_value


def _format_duration(duration_ms: int | None) -> str:
    if duration_ms is None:
        return _EM_DASH
    if duration_ms < 1000:
        return f"{duration_ms} ms"
    total_sec = max(0, duration_ms // 1000)
    minutes, seconds = divmod(total_sec, 60)
    if minutes >= 60:
        hours, minutes = divmod(minutes, 60)
        return f"{hours} hr {minutes} min"
    if minutes:
        return f"{minutes} min {seconds} sec"
    return f"{seconds} sec"


def _format_trigger(trigger_type: str | None) -> str:
    if not trigger_type or not str(trigger_type).strip():
        return "Manual run"
    return str(trigger_type).replace("_", " ").strip().title()


def _esc(value: Any) -> str:
    if value is None:
        return _EM_DASH
    text = str(value).strip()
    return html.escape(text) if text else _EM_DASH


def _table_row(label: str, cell_html: str) -> str:
    return (
        f"<tr>"
        f'<td style="{_TD}"><strong>{html.escape(label)}</strong></td>'
        f'<td style="{_TD}">{cell_html}</td>'
        f"</tr>"
    )


def _table_text_row(label: str, value: Any) -> str:
    return _table_row(label, _esc(value))


def _failed_step_cell(fail: dict[str, Any]) -> str:
    step_label = fail.get("node_label") or fail.get("node_id")
    step_type = fail.get("node_type")
    if not step_label:
        return _EM_DASH
    if step_type:
        return f"{_esc(step_label)} ({_esc(step_type)})"
    return _esc(step_label)


def _error_cell(fail: dict[str, Any], run_error: str | None) -> str:
    message = fail.get("error") or run_error or "No additional details were recorded."
    return f'<span style="color: #B91C1C; font-weight: bold;">{_esc(message)}</span>'


def _run_details_cell(detail_url: str | None) -> str:
    if not detail_url:
        return _EM_DASH
    safe_url = html.escape(detail_url, quote=True)
    return f'<a href="{safe_url}" style="{_LINK}">View run details</a>'


def _workflow_display_name(workflow_id: str, owner_id: str) -> str:
    try:
        wf = db.workflow.get(workflow_id, owner_id)
        if wf and wf.get("name"):
            return wf["name"]
    except Exception:
        logger.debug("[FUSE] Could not load workflow name for failure email", exc_info=True)
    return workflow_id


def _build_failure_email_html(
    *,
    recipient_name: str,
    workflow_name: str,
    run_id: str,
    trigger_type: str,
    triggered_at: str,
    finished_at: str,
    duration_ms: int | None,
    node_count: int,
    nodes_succeeded: int,
    nodes_failed: int,
    fail: dict[str, Any],
    run_error: str | None,
    detail_url: str | None,
) -> str:
    steps_summary = f"{node_count} total, {nodes_succeeded} completed, {nodes_failed} failed"

    rows = [
        _table_text_row("Workflow", workflow_name),
        _table_row("Failed step", _failed_step_cell(fail)),
        _table_row("Error", _error_cell(fail, run_error)),
        *[
            _table_text_row(label, value)
            for label, value in (
                ("Trigger", _format_trigger(trigger_type)),
                ("Started", _format_when(triggered_at)),
                ("Finished", _format_when(finished_at)),
                ("Duration", _format_duration(duration_ms)),
                ("Steps", steps_summary),
            )
        ],
        _table_row("Run ID", f'<span style="word-break: break-all;">{_esc(run_id)}</span>'),
        _table_row("Run details", _run_details_cell(detail_url)),
    ]

    return f"""\
<!DOCTYPE html>
<html>
<body style="{_BODY}">

  <p>Hi {_esc(recipient_name)},</p>

  <p>
    Your workflow did not complete successfully.
    Please find the details below:
  </p>

  <table style="{_TABLE}">
    <tr>
      <th style="{_TH}">Operation</th>
      <th style="{_TH}">Status / Details</th>
    </tr>
{chr(10).join(rows)}
  </table>

  <p>
    Open the run in Fuse Studio to review logs and fix the issue before running again.
  </p>
</body>
</html>"""


def send_workflow_failure_email(
    *,
    owner_id: str,
    workflow_id: str,
    run_id: str,
    trigger_type: str,
    triggered_at: str,
    finished_at: str,
    duration_ms: int | None,
    node_count: int,
    nodes_succeeded: int,
    nodes_failed: int,
    failure: dict[str, Any] | None,
    run_error: str | None,
) -> None:
    """Notify the workflow owner; never raises."""
    if not is_email_service_configured():
        logger.warning("[FUSE] Skipping failure email — email service not configured.")
        return

    to_addr, recipient_name = db.user.get_email_recipient(owner_id)
    if not to_addr:
        logger.warning(
            "[FUSE] Skipping failure email — no email for owner=%s run=%s",
            owner_id,
            run_id,
        )
        return

    workflow_name = _workflow_display_name(workflow_id, owner_id)
    fail = failure or {}

    subject = f'Your workflow "{workflow_name}" could not be completed'
    html_body = apply_get_notified_email_signature(
        _build_failure_email_html(
            recipient_name=recipient_name,
            workflow_name=workflow_name,
            run_id=run_id,
            trigger_type=trigger_type,
            triggered_at=triggered_at,
            finished_at=finished_at,
            duration_ms=duration_ms,
            node_count=node_count,
            nodes_succeeded=nodes_succeeded,
            nodes_failed=nodes_failed,
            fail=fail,
            run_error=run_error,
            detail_url=_run_detail_url(run_id),
        ),
        "text/html",
    )

    try:
        if not send_email(to_addr, subject, html_body, send_as_html=True):
            logger.error(
                "[FUSE] Failure email not sent (email service returned false) — workflow=%s run=%s",
                workflow_id,
                run_id,
            )
            return
        logger.info(
            "[FUSE] Failure notification sent to owner — workflow=%s run=%s",
            workflow_id,
            run_id,
        )
    except Exception:
        logger.exception(
            "[FUSE] Failed to send workflow failure email — workflow=%s run=%s",
            workflow_id,
            run_id,
        )
