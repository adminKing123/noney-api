"""
fuse/nodes/send_webex_message.py
================================
Handler for the "Send Webex Message" action node.
"""

import logging

from .base import NodeHandler
from ..executor import ExecutionContext
from ..variable_resolver import resolve_variables
from db import db
from utils.integrations.webex_utils import (
    get_webex_access_token,
    send_webex_message,
)

logger = logging.getLogger(__name__)


class SendWebexMessageHandler(NodeHandler):
    node_type = "send_webex_message"

    def execute(self, config: dict, context: ExecutionContext) -> dict:
        outputs = context.node_outputs

        send_to = (config.get("send_to") or "room").lower()
        source = (config.get("destination_source") or "pick").lower()
        if source == "pick":
            destination = config.get("destination_pick") or ""
        else:
            destination = config.get("destination") or ""
        destination = resolve_variables(destination, outputs)
        message = resolve_variables(config.get("message", ""), outputs)
        use_markdown = bool(config.get("use_markdown"))

        if not destination or not message:
            raise ValueError("Missing 'destination' or 'message' field.")

        if not context.owner_id:
            raise ValueError("No owner_id in execution context; cannot retrieve Webex integration.")

        integration = db.integration.get_integration(context.owner_id, "webex")
        if not integration or not integration.get("configured"):
            raise ValueError("Webex integration is not configured for this user.")

        access_token = get_webex_access_token(context.owner_id, integration)
        if not access_token:
            raise ValueError("Failed to obtain a valid Webex access token. Please re-authenticate.")

        logger.info(
            "[FUSE] send_webex_message: Sending to %s via %s (workflow=%s run=%s)",
            destination,
            send_to,
            context.workflow_id,
            context.run_id,
        )

        result = send_webex_message(
            access_token=access_token,
            send_to=send_to,
            destination=destination,
            message=message,
            use_markdown=use_markdown,
        )

        return {
            "success": True,
            "message_id": result.get("id"),
            "room_id": result.get("roomId"),
            "person_email": result.get("personEmail"),
            "text": result.get("text") or message,
        }
