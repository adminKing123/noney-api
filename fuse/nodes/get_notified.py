"""
fuse/nodes/get_notified.py
==========================
Web push notification action node handler.

Delivers a real browser push notification to every registered subscription
of the workflow owner via pywebpush + VAPID.

Requires:
  - VAPID_PRIVATE_KEY, VAPID_PUBLIC_KEY, VAPID_CLAIMS_EMAIL set in CONFIG
  - At least one push subscription stored under users/{owner_id}/push_subscriptions
  - pywebpush installed (pip install pywebpush)
"""

import json
import logging

from .base import NodeHandler
from ..variable_resolver import resolve_variables

logger = logging.getLogger(__name__)


class GetNotifiedHandler(NodeHandler):
    """
    Send a web push notification to the workflow owner.

    Output: ``{"success": bool, "sent": int, "failed": int, "title": str, "body": str}``
    """

    def execute(self, config: dict, context) -> dict:
        outputs = context.node_outputs

        # ── Resolve variable tokens in all notification fields ────────────────
        title     = resolve_variables(config.get("title", ""),     outputs)
        body      = resolve_variables(config.get("body", ""),      outputs)
        icon_url  = resolve_variables(config.get("icon_url", ""),  outputs)
        image_url = resolve_variables(config.get("image_url", ""), outputs)
        click_url = resolve_variables(config.get("click_url", ""), outputs)
        cta_label = resolve_variables(config.get("cta_label", ""), outputs)
        require_interaction = bool(config.get("require_interaction", False))

        logger.info(
            "[FUSE] get_notified — workflow=%s run=%s owner=%s title=%r",
            context.workflow_id, context.run_id, context.owner_id, title,
        )

        # ── Guard: owner_id must be set ───────────────────────────────────────
        if not context.owner_id:
            logger.warning(
                "[FUSE] get_notified: no owner_id on context — cannot deliver push."
            )
            return {"success": False, "sent": 0, "failed": 0,
                    "title": title, "body": body, "error": "no owner_id"}

        # ── Guard: VAPID must be configured ───────────────────────────────────
        from config import CONFIG
        if not CONFIG.VAPID_PRIVATE_KEY or not CONFIG.VAPID_PUBLIC_KEY:
            logger.warning(
                "[FUSE] get_notified: VAPID keys not configured — cannot deliver push."
            )
            return {"success": False, "sent": 0, "failed": 0,
                    "title": title, "body": body, "error": "vapid_not_configured"}

        # ── Load subscriptions ────────────────────────────────────────────────
        from db import db
        subscriptions = db.user.get_push_subscriptions(context.owner_id)
        if not subscriptions:
            logger.warning(
                "[FUSE] get_notified: no push subscriptions for owner '%s'.",
                context.owner_id,
            )
            return {"success": False, "sent": 0, "failed": 0,
                    "title": title, "body": body, "error": "no_subscriptions"}

        # ── Build the notification payload ────────────────────────────────────
        payload = {
            "title":               title,
            "body":                body,
            "requireInteraction":  require_interaction,
        }
        if icon_url:
            payload["icon"] = icon_url
        if image_url:
            payload["image"] = image_url
        if click_url:
            payload["url"] = click_url
        if cta_label:
            payload["ctaLabel"] = cta_label

        # ── Deliver to each subscription ──────────────────────────────────────
        from pywebpush import webpush, WebPushException

        vapid_claims = {"sub": CONFIG.VAPID_CLAIMS_EMAIL}
        sent  = 0
        failed = 0
        stale_endpoints: list[str] = []

        for sub in subscriptions:
            endpoint = sub.get("endpoint", "")
            try:
                webpush(
                    subscription_info={
                        "endpoint": endpoint,
                        "keys": sub.get("keys", {}),
                    },
                    data=json.dumps(payload),
                    vapid_private_key=CONFIG.VAPID_PRIVATE_KEY,
                    vapid_claims=vapid_claims,
                )
                sent += 1
                logger.info(
                    "[FUSE] get_notified: push sent to endpoint ...%s", endpoint[-30:]
                )
            except WebPushException as exc:
                failed += 1
                status = getattr(exc.response, "status_code", None)
                logger.warning(
                    "[FUSE] get_notified: push failed (status=%s) endpoint=...%s — %s",
                    status, endpoint[-30:], exc,
                )
                # 410 Gone / 404 = subscription expired; clean it up
                if status in (404, 410):
                    stale_endpoints.append(endpoint)
            except Exception as exc:
                failed += 1
                logger.exception(
                    "[FUSE] get_notified: unexpected error for endpoint ...%s — %s",
                    endpoint[-30:], exc,
                )

        # Remove expired subscriptions asynchronously
        for ep in stale_endpoints:
            try:
                db.user.delete_push_subscription(context.owner_id, ep)
            except Exception:
                pass

        return {
            "success": sent > 0,
            "sent":    sent,
            "failed":  failed,
            "title":   title,
            "body":    body,
        }
