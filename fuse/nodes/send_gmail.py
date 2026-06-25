"""
fuse/nodes/send_gmail.py
========================
Handler for the "Send Gmail" action node.
"""

import logging
import base64
from email.message import EmailMessage
import requests

from .base import NodeHandler
from ..executor import ExecutionContext
from ..variable_resolver import resolve_variables
from db import db
from utils.integrations.gmail_utils import refresh_gmail_access_token_if_expired

logger = logging.getLogger(__name__)

class SendGmailHandler(NodeHandler):
    node_type = "send_gmail"

    def execute(self, config: dict, context: ExecutionContext) -> dict:
        """
        Sends an email using the Gmail API integration.
        Returns {"success": True, "message_id": ...} on success.
        """
        outputs = context.node_outputs
        
        to_email = resolve_variables(config.get("to", ""), outputs)
        subject = resolve_variables(config.get("subject", ""), outputs)
        body = resolve_variables(config.get("body", ""), outputs)

        if not to_email or not subject or not body:
            raise ValueError("Missing 'to', 'subject', or 'body' field.")

        if not context.owner_id:
            raise ValueError("No owner_id in execution context; cannot retrieve Gmail integration.")

        # Get the Gmail integration for the user
        integration = db.integration.get_integration(context.owner_id, "gmail")
        if not integration or not integration.get("configured"):
            raise ValueError("Gmail integration is not configured for this user.")

        # Refresh token if necessary
        integration = refresh_gmail_access_token_if_expired(context.owner_id, integration)
        if not integration or not integration.get("access_token"):
            raise ValueError("Failed to obtain a valid Gmail access token. Please re-authenticate.")

        access_token = integration.get("access_token")

        # Create the email message
        message = EmailMessage()
        message.set_content(body)
        message["To"] = to_email
        message["From"] = integration.get("email", "")  # Or let Gmail default it
        message["Subject"] = subject

        # Encode the message as base64url, which is required by Gmail API
        encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()

        send_url = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        payload = {
            "raw": encoded_message
        }

        logger.info(
            "[FUSE] send_gmail: Sending email to %s (workflow=%s run=%s)",
            to_email, context.workflow_id, context.run_id
        )

        response = requests.post(send_url, headers=headers, json=payload)
        
        if response.status_code not in (200, 201):
            logger.error(
                "[FUSE] send_gmail: Failed to send email (status=%s) - %s",
                response.status_code, response.text
            )
            raise RuntimeError(f"Gmail API error: {response.text}")

        resp_data = response.json()
        return {
            "success": True,
            "message_id": resp_data.get("id"),
            "thread_id": resp_data.get("threadId"),
            "to": to_email,
            "subject": subject
        }
