"""
fuse/nodes/webhook.py
=====================
Webhook starter node handler + request verification.

The ``WebhookHandler.execute()`` method is a no-op during DAG traversal
because the webhook request data is injected directly into
``context.trigger_data`` by the route handler before execution begins.

``verify_webhook_request()`` is called by the route handler BEFORE the
workflow runs.  Supported auth modes:

  none   — allow all requests (default)
  bearer — check `Authorization: Bearer <secret>` header (constant-time)
  basic  — check the password field of `Authorization: Basic <base64>` (constant-time)
  hmac   — GitHub-style HMAC-SHA256 body signature via
           `X-Hub-Signature-256: sha256=<hex>` or `X-Fuse-Signature`
"""

import base64
import hashlib
import hmac as _hmac
import logging

from .base import NodeHandler

logger = logging.getLogger(__name__)


# ─── Handler ───────────────────────────────────────────────────────────────────

class WebhookHandler(NodeHandler):
    """
    Webhook starter node.

    The trigger data (body, headers, query_params, method) is pre-populated
    into ``context.trigger_data`` by the Flask route handler, so this execute()
    just surfaces it as the node's output for downstream variable references.
    """

    def execute(self, config: dict, context) -> dict:  # noqa: ARG002
        logger.info(
            "[FUSE] webhook trigger received — method=%s workflow=%s run=%s",
            context.trigger_data.get("method", "?"),
            context.workflow_id,
            context.run_id,
        )
        logger.info(
            "[FUSE]   body         = %s",
            context.trigger_data.get("body"),
        )
        logger.info(
            "[FUSE]   query_params = %s",
            context.trigger_data.get("query_params"),
        )
        return context.trigger_data


# ─── Auth verification ─────────────────────────────────────────────────────────

def verify_webhook_request(
    config: dict,
    method: str,
    headers: dict,
    body_bytes: bytes,
) -> tuple[bool, str | None]:
    """
    Verify an incoming webhook HTTP request against the node's auth config.

    Args:
        config:     Webhook node config dict (contains auth_type, secret, etc.).
        method:     HTTP method of the incoming request (e.g. "POST").
        headers:    Request headers as a plain dict.
        body_bytes: Raw request body bytes for HMAC verification.

    Returns:
        ``(True, None)`` on success, or ``(False, error_message)`` on failure.
    """
    auth_type = (config.get("auth_type") or "none").lower()
    secret    = config.get("secret", "") or ""

    # ── None ──────────────────────────────────────────────────────────────────
    if auth_type == "none":
        return True, None

    # ── Bearer token ──────────────────────────────────────────────────────────
    if auth_type == "bearer":
        auth_header = _get_header(headers, "Authorization")
        if not auth_header.startswith("Bearer "):
            return False, (
                "Missing or invalid Authorization header "
                "(expected: Authorization: Bearer <token>)"
            )
        provided = auth_header[7:]
        if not secret:
            logger.warning("[FUSE] Bearer auth configured but secret is empty — rejecting.")
            return False, "Webhook secret is not configured on this workflow."
        if not _safe_compare(provided, secret):
            return False, "Bearer token mismatch."
        return True, None

    # ── Basic auth ────────────────────────────────────────────────────────────
    if auth_type == "basic":
        auth_header = _get_header(headers, "Authorization")
        if not auth_header.startswith("Basic "):
            return False, (
                "Missing or invalid Authorization header "
                "(expected: Authorization: Basic <base64(user:password)>)"
            )
        try:
            decoded = base64.b64decode(auth_header[6:]).decode("utf-8", errors="replace")
            _, provided_password = decoded.split(":", 1)
        except Exception:
            return False, "Malformed Basic auth header."
        if not secret:
            return False, "Webhook secret is not configured on this workflow."
        if not _safe_compare(provided_password, secret):
            return False, "Basic auth password mismatch."
        return True, None

    # ── HMAC-SHA256 (GitHub-style) ────────────────────────────────────────────
    if auth_type == "hmac":
        sig_header = (
            _get_header(headers, "X-Hub-Signature-256")
            or _get_header(headers, "X-Fuse-Signature")
        )
        if not sig_header:
            return False, (
                "Missing HMAC signature header. "
                "Send X-Hub-Signature-256: sha256=<hex> or X-Fuse-Signature: sha256=<hex>."
            )
        if not secret:
            return False, "Webhook secret is not configured on this workflow."
        digest  = _hmac.new(secret.encode(), body_bytes, hashlib.sha256).hexdigest()
        expected = f"sha256={digest}"
        if not _safe_compare(sig_header, expected):
            return False, "HMAC signature verification failed."
        return True, None

    # Unknown auth type — log and allow (fail-safe for future types)
    logger.warning("[FUSE] Unknown auth_type '%s' — allowing request.", auth_type)
    return True, None


# ─── Internal helpers ──────────────────────────────────────────────────────────

def _get_header(headers: dict, name: str) -> str:
    """Case-insensitive header lookup, returning '' if absent."""
    lower_name = name.lower()
    for k, v in headers.items():
        if k.lower() == lower_name:
            return v or ""
    return ""


def _safe_compare(a: str, b: str) -> bool:
    """Constant-time string comparison to prevent timing attacks."""
    return _hmac.compare_digest(a.encode(), b.encode())
