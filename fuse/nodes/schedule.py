"""
fuse/nodes/schedule.py
======================
Schedule starter node handler.

Scheduling runs in Cron Service (cron-job.org → cron-service → noney webhook).
"""

import logging

from .base import NodeHandler

logger = logging.getLogger(__name__)


class ScheduleHandler(NodeHandler):
    """Schedule starter — trigger data is injected by the schedule webhook route."""

    def execute(self, config: dict, context) -> dict:  # noqa: ARG002
        logger.info(
            "[FUSE] schedule trigger fired — workflow=%s run=%s fired_at=%s",
            context.workflow_id,
            context.run_id,
            context.trigger_data.get("fired_at", context.triggered_at),
        )
        return context.trigger_data
