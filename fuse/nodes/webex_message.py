"""
fuse/nodes/webex_message.py
===========================
Handler for the "On Webex Message" starter node.

The Webex webhook route injects normalised message data into
``context.trigger_data`` before execution begins, so this handler simply
returns that payload for downstream variable references.
"""

import logging

from .base import NodeHandler

logger = logging.getLogger(__name__)


class WebexMessageHandler(NodeHandler):
    node_type = "webex_message"

    def execute(self, config: dict, context) -> dict:  # noqa: ARG002
        logger.info(
            "[FUSE] webex_message trigger — message_id=%s workflow=%s run=%s",
            context.trigger_data.get("message_id"),
            context.workflow_id,
            context.run_id,
        )
        return context.trigger_data
