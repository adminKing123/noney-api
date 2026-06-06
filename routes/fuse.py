from datetime import datetime

from flask import Blueprint, request, jsonify

from db import db
from fuse.compiler import compile_workflow_graph
from fuse.executor import run_workflow_async
from fuse.nodes.webhook import verify_webhook_request
from fuse.runtime import runtime
from middleware.auth import require_auth
from config import CONFIG

fuse_bp = Blueprint("fuse", __name__, url_prefix="/fuse")


# ─── Workflows ────────────────────────────────────────────────────────────────

@fuse_bp.route("/workflows", methods=["GET"])
@require_auth
def list_workflows():
    """GET /fuse/workflows — list all workflows owned by the authenticated user."""
    owner_id = request.user["uid"]
    workflows = db.workflow.list_for_owner(owner_id)
    return jsonify(workflows)


@fuse_bp.route("/workflows", methods=["POST"])
@require_auth
def create_workflow():
    """POST /fuse/workflows — create a new workflow for the authenticated user."""
    owner_id = request.user["uid"]
    name = (request.json or {}).get("name", "Untitled Workflow").strip() or "Untitled Workflow"
    workflow = db.workflow.create(owner_id=owner_id, name=name)
    return jsonify(workflow), 201


@fuse_bp.route("/workflows/<workflow_id>", methods=["GET"])
@require_auth
def get_workflow(workflow_id):
    """GET /fuse/workflows/:id — fetch a single workflow by ID."""
    owner_id = request.user["uid"]
    workflow = db.workflow.get(workflow_id, owner_id)
    if workflow is None:
        return jsonify({"error": "Workflow not found"}), 404
    return jsonify(workflow)


@fuse_bp.route("/workflows/<workflow_id>/name", methods=["PATCH"])
@require_auth
def update_workflow_name(workflow_id):
    """PATCH /fuse/workflows/:id/name — rename a workflow."""
    owner_id = request.user["uid"]
    name = (request.json or {}).get("name", "").strip()
    if not name:
        return jsonify({"error": "name is required"}), 400
    updated = db.workflow.update_name(workflow_id, owner_id, name)
    if updated is None:
        return jsonify({"error": "Workflow not found"}), 404
    return jsonify(updated)


@fuse_bp.route("/workflows/<workflow_id>/graph", methods=["PATCH"])
@require_auth
def update_workflow_graph(workflow_id):
    """PATCH /fuse/workflows/:id/graph — save the React Flow node/edge graph."""
    owner_id = request.user["uid"]
    body = request.json or {}
    nodes = body.get("nodes", [])
    edges = body.get("edges", [])
    updated = db.workflow.update_graph(workflow_id, owner_id, nodes, edges)
    if updated is None:
        return jsonify({"error": "Workflow not found"}), 404
    return jsonify(updated)


@fuse_bp.route("/workflows/<workflow_id>/status", methods=["PATCH"])
@require_auth
def update_workflow_status(workflow_id):
    """PATCH /fuse/workflows/:id/status — toggle active / inactive (raw DB flag only).

    NOTE: prefer /activate and /deactivate for production use — those endpoints
    compile the graph and start/stop the execution engine.  This endpoint exists
    as an escape hatch for simple status overrides.
    """
    owner_id = request.user["uid"]
    status = (request.json or {}).get("status", "")
    if status not in ("active", "inactive"):
        return jsonify({"error": "status must be 'active' or 'inactive'"}), 400
    updated = db.workflow.update_status(workflow_id, owner_id, status)
    if updated is None:
        return jsonify({"error": "Workflow not found"}), 404
    return jsonify(updated)


# ─── Execution control ────────────────────────────────────────────────────────

@fuse_bp.route("/workflows/<workflow_id>/activate", methods=["POST"])
@require_auth
def activate_workflow(workflow_id):
    """
    POST /fuse/workflows/:id/activate
    ─────────────────────────────────
    Compile the current graph, register it in the RuntimeManager, and set the
    workflow status to 'active'.

    If a previous execution exists (e.g. the workflow is being recompiled after
    a graph edit) it is stopped first so the new graph takes effect immediately.

    Response (200):
        {
            "success":     true,
            "workflow":    { ... },
            "compiled_at": "<ISO-8601>",
            "graph_hash":  "<sha256>",
            "webhook_url": "<url> | null"
        }

    Response (400) on validation failure:
        { "success": false, "errors": ["<message>", ...] }
    """
    owner_id = request.user["uid"]
    workflow = db.workflow.get(workflow_id, owner_id)
    if workflow is None:
        return jsonify({"error": "Workflow not found"}), 404

    nodes = workflow.get("nodes", []) or []
    edges = workflow.get("edges", []) or []

    # ── 1. Compile ────────────────────────────────────────────────────────────
    compiled_graph, errors = compile_workflow_graph(nodes, edges, workflow_id, owner_id)
    if errors:
        return jsonify({"success": False, "errors": errors}), 400

    # ── 2. Start execution (stops any prior execution first) ─────────────────
    try:
        runtime.activate(workflow_id, compiled_graph)
    except Exception as exc:
        return jsonify({"success": False, "errors": [str(exc)]}), 500

    # ── 3. Persist compilation state ──────────────────────────────────────────
    updated = db.workflow.save_compilation(
        workflow_id    = workflow_id,
        owner_id       = owner_id,
        compiled_graph = compiled_graph,
        graph_hash     = compiled_graph["graph_hash"],
        compiled_at    = compiled_graph["compiled_at"],
    )

    # ── 4. Build webhook URL (only relevant for webhook-triggered workflows) ──
    starter_type = compiled_graph["starter"]["node_type"]
    webhook_url = None
    if starter_type == "webhook":
        base = CONFIG.HOST.rstrip("/")
        webhook_url = f"{base}/fuse/webhook/{workflow_id}"

    return jsonify({
        "success":     True,
        "workflow":    updated,
        "compiled_at": compiled_graph["compiled_at"],
        "graph_hash":  compiled_graph["graph_hash"],
        "webhook_url": webhook_url,
    })


@fuse_bp.route("/workflows/<workflow_id>/deactivate", methods=["POST"])
@require_auth
def deactivate_workflow(workflow_id):
    """
    POST /fuse/workflows/:id/deactivate
    ─────────────────────────────────────
    Stop the workflow execution and set status to 'inactive'.

    Response (200):
        { "success": true, "workflow": { ... } }
    """
    owner_id = request.user["uid"]
    workflow = db.workflow.get(workflow_id, owner_id)
    if workflow is None:
        return jsonify({"error": "Workflow not found"}), 404

    runtime.deactivate(workflow_id)
    updated = db.workflow.update_status(workflow_id, owner_id, "inactive")
    return jsonify({"success": True, "workflow": updated})


# ─── Public webhook trigger ───────────────────────────────────────────────────

@fuse_bp.route(
    "/webhook/<workflow_id>",
    methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
)
def trigger_webhook(workflow_id):
    """
    /fuse/webhook/<workflow_id>  (all HTTP methods)
    ────────────────────────────────────────────────
    Public endpoint called by external services to trigger a webhook workflow.

    Authentication is NOT handled by Firebase here — instead the webhook node's
    ``auth_type`` config controls how the request is verified:
      none   — accept all
      bearer — validate Authorization: Bearer <secret>
      basic  — validate Authorization: Basic <base64>
      hmac   — validate X-Hub-Signature-256 / X-Fuse-Signature header

    The workflow runs asynchronously (daemon thread) so this endpoint always
    returns almost immediately.

    The response status code is taken from the webhook node's ``response_code``
    config (default 202 Accepted).

    Errors:
        404 — workflow not found or not active
        400 — workflow starter is not a webhook
        401 — auth verification failed
        405 — HTTP method does not match node config
    """
    execution = runtime.get_execution(workflow_id)
    if execution is None:
        return jsonify({"error": "Workflow not found or not active."}), 404

    compiled_graph = execution.compiled_graph
    starter        = compiled_graph.get("starter", {})

    if starter.get("node_type") != "webhook":
        return jsonify({"error": "This workflow is not webhook-triggered."}), 400

    starter_config  = starter.get("config", {})
    expected_method = (starter_config.get("method") or "POST").upper()

    # ── Verify HTTP method ────────────────────────────────────────────────────
    if request.method != expected_method:
        return jsonify({
            "error": f"Method {request.method} not allowed. This webhook expects {expected_method}.",
        }), 405

    # ── Verify auth ───────────────────────────────────────────────────────────
    body_bytes = request.get_data()
    is_valid, auth_error = verify_webhook_request(
        config     = starter_config,
        method     = request.method,
        headers    = dict(request.headers),
        body_bytes = body_bytes,
    )
    if not is_valid:
        return jsonify({"error": auth_error}), 401

    # ── Build trigger data ────────────────────────────────────────────────────
    try:
        # force=True: parse JSON regardless of Content-Type so requests sent
        # without an explicit application/json header still work correctly.
        body = request.get_json(force=True, silent=True) or {}
    except Exception:
        body = {}

    # Strip sensitive headers before passing downstream
    _SENSITIVE = frozenset({"authorization", "cookie", "x-api-key"})
    safe_headers = {k: v for k, v in request.headers.items() if k.lower() not in _SENSITIVE}

    trigger_data = {
        "body":         body,
        "headers":      safe_headers,
        "query_params": dict(request.args),
        "method":       request.method,
        "triggered_at": datetime.utcnow().isoformat() + "Z",
    }

    # ── Execute asynchronously ────────────────────────────────────────────────
    run_workflow_async(compiled_graph, trigger_data)

    response_code = int(starter_config.get("response_code") or 202)
    return jsonify({"status": "accepted", "workflow_id": workflow_id}), response_code


@fuse_bp.route("/workflows/<workflow_id>", methods=["DELETE"])
@require_auth
def delete_workflow(workflow_id):
    """DELETE /fuse/workflows/:id — permanently remove a workflow."""
    owner_id = request.user["uid"]
    success = db.workflow.delete(workflow_id, owner_id)
    if not success:
        return jsonify({"error": "Workflow not found"}), 404
    return jsonify({"success": True, "id": workflow_id})


# ─── Node definitions (static, no DB needed) ─────────────────────────────────

STARTER_NODES = [
    {
        "type": "schedule",
        "label": "On a Schedule",
        "icon": "TbCalendarTime",
        "description": "Start at a set date and time. Have it run once or repeat on a schedule.",
        "config_form": {
            "presets": [
                {"label": "Monday at 8 AM",  "values": {"date": "next-monday", "time": "08:00", "repeat": "weekly_monday", "ends": "1y"}},
                {"label": "Weekdays at 8 AM", "values": {"date": "today",       "time": "08:00", "repeat": "weekdays",      "ends": "1y"}},
                {"label": "In 5 minutes",     "values": {"date": "today",       "time": "+5min", "repeat": "none",          "ends": "1y"}},
            ],
            "sections": [
                {
                    "title": "Start date and time",
                    "layout": "grid-2",
                    "fields": [
                        {"key": "date", "label": "Date", "type": "date", "required": True, "hint": "MM/DD/YYYY"},
                        {"key": "time", "label": "Time", "type": "time", "required": True},
                    ],
                },
                {
                    "fields": [
                        {
                            "key": "repeat", "label": "Repeat", "type": "select", "required": True,
                            "options": [
                                {"label": "Does not repeat",       "value": "none"},
                                {"label": "Hourly",                "value": "hourly"},
                                {"label": "Daily",                 "value": "daily"},
                                {"label": "Weekly on Monday",      "value": "weekly_monday"},
                                {"label": "Weekdays (Mon\u2013Fri)", "value": "weekdays"},
                                {"label": "Monthly",               "value": "monthly"},
                                {"label": "Annually",              "value": "annually"},
                            ],
                            "after_hint": "For daily and less frequent repeats, runs start within 3 minutes of the set time",
                        },
                        {
                            "key": "ends", "label": "Ends", "type": "select",
                            "options": [
                                {"label": "1 year",  "value": "1y"},
                                {"label": "6 months","value": "6m"},
                                {"label": "3 months","value": "3m"},
                                {"label": "1 month", "value": "1m"},
                                {"label": "Never",   "value": "never"},
                            ],
                        },
                        {"key": "timezone", "label": "Time zone", "type": "timezone_select", "required": True},
                    ],
                },
            ],
        },
    },
    {
        "type": "webhook",
        "label": "On Webhook",
        "icon": "TbWebhook",
        "description": "Start the workflow whenever an HTTP request hits the generated webhook URL.",
        "config_form": {
            "sections": [
                {
                    "title": "Endpoint",
                    "fields": [
                        {
                            "key": "method", "label": "HTTP Method", "type": "select", "required": True,
                            "options": [
                                {"label": "POST",  "value": "POST"},
                                {"label": "GET",   "value": "GET"},
                                {"label": "PUT",   "value": "PUT"},
                                {"label": "PATCH", "value": "PATCH"},
                            ],
                            "hint": "Only requests matching this method will trigger the workflow",
                        },
                    ],
                },
                {
                    "title": "Security",
                    "fields": [
                        {
                            "key": "auth_type", "label": "Authentication", "type": "select",
                            "options": [
                                {"label": "None",             "value": "none"},
                                {"label": "Bearer token",     "value": "bearer"},
                                {"label": "Basic auth",       "value": "basic"},
                                {"label": "HMAC signature",   "value": "hmac"},
                            ],
                            "hint": "How the webhook verifies that the request is from a trusted sender",
                        },
                        {"key": "secret", "label": "Secret / Token", "type": "text", "placeholder": "Paste your secret here", "hint": "Used to verify the HMAC signature or as the expected bearer token"},
                    ],
                },
                {
                    "title": "Response",
                    "fields": [
                        {"key": "response_code", "label": "Status Code", "type": "number", "placeholder": "200", "hint": "HTTP status returned immediately to the caller"},
                    ],
                },
                {
                    "title": "Body Schema",
                    "fields": [
                        {
                            "key": "body_schema", "label": "Incoming Body Fields", "type": "body_builder",
                            "hint": "Define the fields you expect in the webhook request body. These become variables you can reference in downstream nodes using {{webhook.body.fieldName}}.",
                        },
                    ],
                },
            ],
        },
    },
]

ACTION_NODES = [
    {
        "type": "get_notified",
        "label": "Get Notified",
        "icon": "TbBell",
        "section": "Notifications",
        "description": "Send a web push notification to yourself when this workflow step is reached.",
        "config_form": {
            "sections": [
                {
                    "title": "Content",
                    "fields": [
                        {"key": "title",     "label": "Title",            "type": "variable_text",     "placeholder": "e.g. Your report is ready",        "required": True, "hint": "Short headline shown in bold. Use @ to insert a variable."},
                        {"key": "body",      "label": "Body",             "type": "variable_textarea", "placeholder": "e.g. The weekly sales report has been generated.", "required": True, "hint": "Main notification text. Use @ to insert a variable."},
                        {"key": "icon_url",  "label": "Icon URL",         "type": "variable_text",     "placeholder": "https://example.com/icon-192.png",  "hint": "Square image (192\u00d7192 px recommended) shown beside the notification"},
                        {"key": "image_url", "label": "Banner Image URL", "type": "variable_text",     "placeholder": "https://example.com/banner.png",    "hint": "Large image displayed below the body on supported browsers"},
                    ],
                },
                {
                    "title": "Action",
                    "fields": [
                        {"key": "click_url", "label": "Click URL",    "type": "variable_text", "placeholder": "https://app.example.com/dashboard", "hint": "Page to open when the notification is clicked; defaults to the app URL"},
                        {"key": "cta_label", "label": "Button Label", "type": "variable_text", "placeholder": "e.g. View Report",                  "hint": "Optional action button shown inside the notification"},
                    ],
                },
                {
                    "title": "Options",
                    "layout": "grid-2",
                    "fields": [
                        {
                            "key": "require_interaction", "label": "Require Interaction", "type": "select",
                            "options": [
                                {"label": "No \u2014 dismiss automatically", "value": "false"},
                                {"label": "Yes \u2014 stay until dismissed",  "value": "true"},
                            ],
                            "hint": "Keep the notification visible until the user actively dismisses it",
                        },
                        {"key": "ttl_seconds", "label": "Time to Live (sec)", "type": "number", "placeholder": "86400", "hint": "How long the browser retries delivery if you are offline"},
                    ],
                },
            ],
        },
    },
    {
        "type": "if_else",
        "label": "If / Else",
        "icon": "TbGitBranch",
        "section": "Logic",
        "description": "Branch the workflow based on a condition. The True path runs when the condition passes; the False path runs otherwise.",
        "config_form": {
            "sections": [
                {
                    "title": "Condition",
                    "fields": [
                        {
                            "key": "condition", "label": "Condition", "type": "condition_builder",
                            "hint": "Select a variable, choose an operator, and (if needed) enter a comparison value. Connect the True and False handles on the node to route each branch.",
                        },
                    ],
                },
            ],
        },
    },
]


@fuse_bp.route("/nodes/starter", methods=["GET"])
@require_auth
def get_starter_nodes():
    """GET /fuse/nodes/starter — returns all starter node definitions."""
    return jsonify(STARTER_NODES)


@fuse_bp.route("/nodes/actions", methods=["GET"])
@require_auth
def get_action_nodes():
    """GET /fuse/nodes/actions — returns all action node definitions."""
    return jsonify(ACTION_NODES)


# ─── Web Push subscription management ────────────────────────────────────────

@fuse_bp.route("/push/vapid-public-key", methods=["GET"])
@require_auth
def get_vapid_public_key():
    """GET /fuse/push/vapid-public-key — return the server's VAPID public key."""
    if not CONFIG.VAPID_PUBLIC_KEY:
        return jsonify({"error": "Push notifications not configured on this server"}), 503
    return jsonify({"public_key": CONFIG.VAPID_PUBLIC_KEY})


@fuse_bp.route("/push/subscribe", methods=["POST"])
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


@fuse_bp.route("/push/unsubscribe", methods=["POST"])
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
