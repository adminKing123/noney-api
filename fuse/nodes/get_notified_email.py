"""
fuse/nodes/get_notified_email.py
================================
Send an email notification via the app email service when a workflow step runs.
"""

import logging

from db import db
from .base import NodeHandler
from ..variable_resolver import resolve_variables
from utils.email_service import (
    apply_get_notified_email_signature,
    is_email_service_configured,
    send_fuse_workflow_email,
)

logger = logging.getLogger(__name__)


class GetNotifiedEmailHandler(NodeHandler):
    node_type = "get_notified_email"

    def execute(self, config: dict, context) -> dict:
        outputs = context.node_outputs

        if not context.owner_id:
            raise RuntimeError(
                "Cannot send email notification: workflow owner is unknown."
            )

        to_addr = db.user.get_email(context.owner_id)
        if not to_addr:
            raise RuntimeError(
                "Cannot send email notification: no email on file for the workflow owner."
            )

        subject = resolve_variables(config.get("subject", ""), outputs)
        body = resolve_variables(config.get("body", ""), outputs)
        sub_type = config.get("content_type", "text/plain")

        if not is_email_service_configured():
            raise RuntimeError(
                "Email service is not configured on the server "
                "(EMAIL_SERVICE_HOST / EMAIL_SERVICE_API_KEY)."
            )

        body = apply_get_notified_email_signature(body, sub_type)

        logger.info(
            "[FUSE] get_notified_email — workflow=%s run=%s to=%s subject=%r",
            context.workflow_id,
            context.run_id,
            to_addr,
            subject,
        )

        return send_fuse_workflow_email(
            to_addr,
            subject,
            body,
            content_subtype=sub_type,
        )
