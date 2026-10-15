"""
fuse/nodes/switch.py
====================
Switch node — evaluate ordered cases; first match wins, else ``default`` branch.

Output: ``{"matched_handle": str, "matched_index": int | None, "matched_label": str | None}``
"""

import logging

from .base import NodeHandler
from .if_else import evaluate_condition

logger = logging.getLogger(__name__)


class SwitchHandler(NodeHandler):
    def execute(self, config: dict, context) -> dict:
        cases = config.get("cases") or []
        matched_handle = "default"
        matched_index = None
        matched_label = None

        for idx, case in enumerate(cases):
            case_id = (case.get("id") or f"case_{idx}").strip()
            condition = case.get("condition") or {}
            if evaluate_condition(condition, context.node_outputs):
                matched_handle = case_id
                matched_index = idx
                matched_label = case.get("label") or case_id
                logger.info(
                    "[FUSE] switch matched case %s (%s) — workflow=%s run=%s",
                    case_id,
                    matched_label,
                    context.workflow_id,
                    context.run_id,
                )
                break

        if matched_index is None:
            logger.info(
                "[FUSE] switch — no case matched, using default — workflow=%s run=%s",
                context.workflow_id,
                context.run_id,
            )

        return {
            "matched_handle": matched_handle,
            "matched_index": matched_index,
            "matched_label": matched_label,
        }
