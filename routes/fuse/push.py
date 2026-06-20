from flask import Blueprint, request, jsonify
from middleware.auth import require_auth
from db import db
from config import CONFIG

bp = Blueprint("fuse_push", __name__)

# ─── Web Push subscription management ────────────────────────────────────────

@bp.route("/push/vapid-public-key", methods=["GET"])
@require_auth
def get_vapid_public_key():
    """GET /fuse/push/vapid-public-key — return the server's VAPID public key."""
    if not CONFIG.VAPID_PUBLIC_KEY:
        return jsonify({"error": "Push notifications not configured on this server"}), 503
    return jsonify({"public_key": CONFIG.VAPID_PUBLIC_KEY})


@bp.route("/push/subscribe", methods=["POST"])
@require_auth
def push_subscribe():
    """
    POST /fuse/push/subscribe
    ─────────────────────────
    Save (or refresh) the caller's browser push subscription.

    Body: the PushSubscription JSON from the browser:
    {
        "endpoint": "https://...",
        "keys": { "p256dh": "...", "auth": "..." }
    }
    """
    uid          = request.user["uid"]
    subscription = request.get_json(force=True, silent=True) or {}

    if not subscription.get("endpoint"):
        return jsonify({"error": "Invalid subscription object"}), 400

    db.user.save_push_subscription(uid, subscription)
    return jsonify({"success": True})


@bp.route("/push/unsubscribe", methods=["POST"])
@require_auth
def push_unsubscribe():
    """
    POST /fuse/push/unsubscribe
    ────────────────────────────
    Remove the caller's push subscription by endpoint URL.

    Body: { "endpoint": "https://..." }
    """
    uid      = request.user["uid"]
    body     = request.get_json(force=True, silent=True) or {}
    endpoint = body.get("endpoint", "")

    if not endpoint:
        return jsonify({"error": "endpoint required"}), 400

    db.user.delete_push_subscription(uid, endpoint)
    return jsonify({"success": True})
