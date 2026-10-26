"""
fuse/workflow_failure_email.py
==============================
Best-effort email to the workflow owner when a run fails.
"""

from __future__ import annotations

import html
import json
import logging
from typing import Any

from config import CONFIG
from db import db
from utils.email_service import is_email_service_configured, send_email

logger = logging.getLogger(__name__)


def _run_detail_url(run_id: str) -> str | None:
    base = (CONFIG.FRONTEND_URL or "").strip().rstrip("/")
    if not base:
        return None
    return f"{base}/fuse/runs/{run_id}"


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

    to_addr = db.user.get_email(owner_id)
    if not to_addr:
        logger.warning(
            "[FUSE] Skipping failure email — no email for owner=%s run=%s",
            owner_id,
            run_id,
        )
        return

    workflow_name = workflow_id
    try:
        wf = db.workflow.get(workflow_id, owner_id)
        if wf and wf.get("name"):
            workflow_name = wf["name"]
    except Exception:
        logger.debug("[FUSE] Could not load workflow name for failure email", exc_info=True)

    fail = failure or {}
    meta = {
        "workflow_id": workflow_id,
        "workflow_name": workflow_name,
        "run_id": run_id,
        "trigger_type": trigger_type,
        "triggered_at": triggered_at,
        "finished_at": finished_at,
        "duration_ms": duration_ms,
        "node_count": node_count,
        "nodes_succeeded": nodes_succeeded,
        "nodes_failed": nodes_failed,
        "failed_node_id": fail.get("node_id"),
        "failed_node_label": fail.get("node_label"),
        "failed_node_type": fail.get("node_type"),
        "error_type": fail.get("error_type"),
        "error": fail.get("error") or run_error,
    }

    detail_url = _run_detail_url(run_id)
    meta_lines = json.dumps(meta, indent=2, default=str)
    body_parts = [
        f'Your workflow "{workflow_name}" did not complete successfully.',
        "",
        "Summary",
        f"  Run ID:     {run_id}",
        f"  Trigger:    {trigger_type}",
        f"  Started:    {triggered_at}",
        f"  Finished:   {finished_at}",
    ]
    if duration_ms is not None:
        body_parts.append(f"  Duration:   {duration_ms} ms")
    body_parts.extend(
        [
            f"  Nodes:      {node_count} total, {nodes_succeeded} succeeded, {nodes_failed} failed",
            "",
        ]
    )
    if fail.get("node_label") or fail.get("error"):
        body_parts.extend(
            [
                "First failure",
                f"  Step:       {fail.get('node_label') or '—'} ({fail.get('node_type') or '—'})",
                f"  Error type: {fail.get('error_type') or '—'}",
                f"  Message:    {fail.get('error') or run_error or '—'}",
                "",
            ]
        )
    if detail_url:
        body_parts.extend([f"Open run: {detail_url}", ""])
    body_parts.extend(["Metadata (JSON):", meta_lines])

    subject = f'Workflow failed: {workflow_name}'
    plain = "\n".join(body_parts)
    html_body = (
        '<pre style="font-family: sans-serif; white-space: pre-wrap;">'
        f"{html.escape(plain)}"
        "</pre>"
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
