"""
fuse/nodes/get_notified_email.py
================================
Send an email notification via app SMTP when a workflow step runs.
"""

import logging

from db import db
from .base import NodeHandler
from ..variable_resolver import resolve_variables
from utils.email_service import (
    apply_get_notified_email_signature,
    is_smtp_configured,
    send_email,
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

        if not is_smtp_configured():
            raise RuntimeError(
                "SMTP is not configured on the server (SMTP_HOST / SMTP_USER / SMTP_APP_PASSWORD)."
            )

        body = apply_get_notified_email_signature(body, sub_type)

        logger.info(
            "[FUSE] get_notified_email — workflow=%s run=%s to=%s subject=%r",
            context.workflow_id,
            context.run_id,
            to_addr,
            subject,
        )

        meta = send_email(
            to=to_addr,
            subject=subject,
            body=body,
            content_subtype=sub_type,
        )
        return meta
