"""
fuse/nodes/get_notified.py
==========================
Push-notification action node handler (currently mocked).

All ``variable_text`` / ``variable_textarea`` fields are resolved against the
current execution context before logging.  When a real push-notification service
is integrated (e.g. pywebpush), replace the TODO section below with the actual
delivery call.
"""

import logging

from .base import NodeHandler
from ..variable_resolver import resolve_variables

logger = logging.getLogger(__name__)


class GetNotifiedHandler(NodeHandler):
    """
    Send a push notification to the workflow owner.

    **Currently mocked** — instead of delivering a real notification the
    handler prints a formatted summary and logs at INFO level.  To enable real
    delivery, implement the TODO section and add the necessary push-subscription
    data to the user model.

    Output: ``{"success": True, "sent": True, "title": str, "body": str}``
    """

    def execute(self, config: dict, context) -> dict:
        outputs = context.node_outputs

        # ── Resolve all variable tokens in the notification fields ────────────
        title     = resolve_variables(config.get("title", ""),     outputs)
        body      = resolve_variables(config.get("body", ""),      outputs)
        icon_url  = resolve_variables(config.get("icon_url", ""),  outputs)
        image_url = resolve_variables(config.get("image_url", ""), outputs)
        click_url = resolve_variables(config.get("click_url", ""), outputs)
        cta_label = resolve_variables(config.get("cta_label", ""), outputs)

        # ── TODO: replace this block with a real web-push delivery ───────────
        #
        #   Example (pywebpush):
        #     from pywebpush import webpush, WebPushException
        #     subscription = db.user.get_push_subscription(context.owner_id)
        #     webpush(
        #         subscription_info=subscription,
        #         data=json.dumps({"title": title, "body": body, ...}),
        #         vapid_private_key=CONFIG.VAPID_PRIVATE_KEY,
        #         vapid_claims={"sub": "mailto:..."},
        #     )
        #
        # ── MOCK: print + log ────────────────────────────────────────────────
        separator = "=" * 60
        print(
            f"\n{separator}\n"
            f"[FUSE] Push notification (MOCK) sent to user\n"
            f"  Workflow  : {context.workflow_id}\n"
            f"  Run       : {context.run_id}\n"
            f"  Title     : {title}\n"
            f"  Body      : {body}\n"
            f"  Icon URL  : {icon_url or '—'}\n"
            f"  Image URL : {image_url or '—'}\n"
            f"  Click URL : {click_url or '—'}\n"
            f"  CTA Label : {cta_label or '—'}\n"
            f"{separator}\n"
        )
        logger.info(
            "[FUSE] get_notified (mock) — workflow=%s run=%s",
            context.workflow_id, context.run_id,
        )
        logger.info("[FUSE]   title     = %r", title)
        logger.info("[FUSE]   body      = %r", body)
        logger.info("[FUSE]   icon_url  = %r", icon_url or None)
        logger.info("[FUSE]   image_url = %r", image_url or None)
        logger.info("[FUSE]   click_url = %r", click_url or None)
        logger.info("[FUSE]   cta_label = %r", cta_label or None)
        # ── END MOCK ──────────────────────────────────────────────────────────

        return {
            "success": True,
            "sent":    True,
            "title":   title,
            "body":    body,
        }
