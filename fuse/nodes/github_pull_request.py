"""
fuse/nodes/github_pull_request.py
===========================
Handler for the "On GitHub PR" starter node.

The GitHub webhook route injects normalised PR data into
``context.trigger_data`` before execution begins, so this handler simply
returns that payload for downstream variable references.
"""

import logging
from .base import NodeHandler

logger = logging.getLogger(__name__)

class GithubPullRequestHandler(NodeHandler):
    node_type = "github_pull_request"

    def execute(self, config: dict, context) -> dict:  # noqa: ARG002
        logger.info(
            "[FUSE] github_pull_request trigger — pr_id=%s workflow=%s run=%s",
            context.trigger_data.get("pr_id"),
            context.workflow_id,
            context.run_id,
        )
        return context.trigger_data
