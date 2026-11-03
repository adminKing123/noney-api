"""Teardown Cron Service schedules (mirrors Webex webhook cleanup)."""

from __future__ import annotations

import logging

from utils.cron_service import delete_workflow_schedule

logger = logging.getLogger(__name__)


def cleanup_cron_schedule_workflow(workflow_id: str) -> None:
    """Remove cron-job.org registration for a workflow (best-effort)."""
    if not workflow_id:
        return
    try:
        delete_workflow_schedule(workflow_id)
        logger.info("[FUSE] Cron schedule removed for workflow '%s'.", workflow_id)
    except Exception:
        logger.exception("[FUSE] Failed to remove cron schedule for '%s'.", workflow_id)
