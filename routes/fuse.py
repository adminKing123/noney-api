import requests
import urllib.parse
from datetime import datetime, timedelta

from flask import Blueprint, request, jsonify, redirect
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
    """
    GET /fuse/workflows
    ────────────────────
    List workflows owned by the authenticated user, newest first.

    Query params:
        limit           (int, default 20, max 100)
        after_created_at (str ISO-8601)  \u2500 cursor from previous page
        after_id        (str)            ┘
    """
    owner_id = request.user["uid"]

    try:
        limit = min(int(request.args.get("limit", 20)), 100)
    except (ValueError, TypeError):
        limit = 20

    after_created_at = request.args.get("after_created_at") or None
    after_id         = request.args.get("after_id") or None

    result = db.workflow.list_for_owner(
        owner_id,
        limit=limit,
        after_created_at=after_created_at,
        after_id=after_id,
    )
    return jsonify(result)

@fuse_bp.route("/discover", methods=["GET"])
@require_auth
def discover_workflows():
    """
    GET /fuse/discover
    """
    owner_id = request.user["uid"]

    limit = 15

    workflows = db.workflow.list_for_owner(
        owner_id,
        limit=limit,
    )
    return jsonify({
        "workflows": workflows,
    })


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

    # ── 2. Save an immutable compiled-graph version ───────────────────────────
    version = db.workflow_version.save(
        workflow_id    = workflow_id,
        owner_id       = owner_id,
        graph_hash     = compiled_graph["graph_hash"],
        compiled_graph = compiled_graph,
    )
    # Embed the version_id so the executor can link each run to this version
    compiled_graph["version_id"] = version["version_id"]

    # ── 3. Start execution (stops any prior execution first) ─────────────────
    try:
        runtime.activate(workflow_id, compiled_graph)
    except Exception as exc:
        return jsonify({"success": False, "errors": [str(exc)]}), 500

    # ── 4. Persist compilation state on the workflow doc ──────────────────────
    updated = db.workflow.save_compilation(
        workflow_id    = workflow_id,
        owner_id       = owner_id,
        compiled_graph = compiled_graph,
        graph_hash     = compiled_graph["graph_hash"],
        compiled_at    = compiled_graph["compiled_at"],
    )

    # ── 5. Build webhook URL (only relevant for webhook-triggered workflows) ──
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
        "version_id":  version["version_id"],
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
        "label": "Check If",
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
                            "hint": "Add one or more conditions. Use the AND / OR toggle between rows to control how they combine. Connect the True and False handles on the node to route each branch.",
                        },
                    ],
                },
            ],
        },
    },
    {
        "type": "ai_structured_output",
        "label": "AI Structured Output",
        "icon": "TbSparkles",
        "section": "AI",
        "description": "Generate structured output from a prompt using AI. Define the expected JSON schema with descriptions for the AI to follow.",
        "config_form": {
            "sections": [
                {
                    "title": "Prompt",
                    "fields": [
                        {
                            "key": "prompt", 
                            "label": "Prompt", 
                            "type": "variable_textarea", 
                            "placeholder": "Extract information from the provided text...", 
                            "required": True,
                            "hint": "Instructions for the AI. Use @ to insert variables."
                        },
                    ],
                },
                {
                    "title": "Output Schema",
                    "fields": [
                        {
                            "key": "output_schema", 
                            "label": "JSON Schema", 
                            "type": "body_builder", 
                            "showDescription": True,
                            "showEnum": True,
                            "hint": "Define the structure and properties you expect the AI to return. Provide descriptions to help the AI understand the purpose of each field."
                        },
                    ],
                },
            ],
        },
    },
    {
        "type": "http_request",
        "label": "HTTP Request",
        "icon": "TbWorldWww",
        "section": "Network",
        "description": "Make an outbound HTTP request to any URL. Map response fields to variables for use in downstream nodes.",
        "config_form": {
            "sections": [
                {
                    "title": "Endpoint",
                    "fields": [
                        {
                            "key": "method",
                            "label": "Method",
                            "type": "select",
                            "options": [
                                {"label": "GET",    "value": "GET"},
                                {"label": "POST",   "value": "POST"},
                                {"label": "PUT",    "value": "PUT"},
                                {"label": "PATCH",  "value": "PATCH"},
                                {"label": "DELETE", "value": "DELETE"},
                            ],
                        },
                        {
                            "key": "url",
                            "label": "URL",
                            "type": "variable_text",
                            "placeholder": "https://api.example.com/endpoint",
                            "required": True,
                            "hint": "The full URL to request. Use @ to insert a variable.",
                        },
                    ],
                },
                {
                    "title": "Query Parameters",
                    "fields": [
                        {
                            "key": "query_params",
                            "label": "Parameters",
                            "type": "json_value_builder",
                            "hint": "Appended to the URL as ?key=value pairs. Use @ to insert variables into values.",
                        },
                    ],
                },
                {
                    "title": "Headers",
                    "fields": [
                        {
                            "key": "headers",
                            "label": "Headers",
                            "type": "json_value_builder",
                            "hint": "HTTP headers sent with the request (e.g. Authorization, Content-Type). Use @ to insert variables.",
                        },
                    ],
                },
                {
                    "title": "Request Body",
                    "fields": [
                        {
                            "key": "payload",
                            "label": "Body Fields",
                            "type": "json_value_builder",
                            "hint": "Define the JSON body to send (POST, PUT, PATCH). Set key, type and value for each field \u2014 use @ to insert variables.",
                        },
                    ],
                },
                {
                    "title": "Response",
                    "fields": [
                        {
                            "key": "response_schema",
                            "label": "Expected Response Fields",
                            "type": "body_builder",
                            "hint": "Declare the fields you expect in the JSON response. Each top-level field becomes a variable: {{node_id.fieldName}}.",
                        },
                        {
                            "key": "timeout",
                            "label": "Timeout (seconds)",
                            "type": "number",
                            "placeholder": "30",
                            "hint": "Maximum seconds to wait for a response before the node fails.",
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


# ─── Integrations ─────────────────────────────────────────────────────────────

INTEGRATION_NODES = [
    {
        "id": "gmail",
        "name": "Gmail Connect",
        "description": "Connect your Gmail account to send and receive emails.",
        "icon": "SiGmail",
        "configured": False
    },
    {
        "id": "webex",
        "name": "Webex Connect",
        "description": "Connect your Webex account to send messages and notifications.",
        "icon": "SiWebex",
        "configured": False
    }
]

@fuse_bp.route("/integration", methods=["GET"])
@require_auth
def get_integrations():
    """GET /fuse/integration — returns list of integration nodes and their config status."""
    user_id = request.user["uid"]
    
    # Check configured status for each integration
    configured_integrations = []
    for integration in INTEGRATION_NODES:
        db_integration = db.integration.get_integration(user_id, integration["id"])
        
        # Integration is considered configured if we have it in the DB and it's marked as configured
        is_configured = False
        if db_integration and db_integration.get("configured", False):
            is_configured = True
            
        configured_integration = dict(integration)
        configured_integration["configured"] = is_configured
        configured_integrations.append(configured_integration)
        
    return jsonify(configured_integrations)

# ─── Gmail OAuth ──────────────────────────────────────────────────────────────

@fuse_bp.route("/integration/gmail/auth", methods=["GET"])
@require_auth
def gmail_oauth_start():
    """GET /fuse/integration/gmail/auth — starts the Google OAuth flow."""
    user_id = request.user["uid"]
    
    client_id = CONFIG.GOOGLE_OAUTH_CLIENT_ID
    redirect_uri = CONFIG.GOOGLE_OAUTH_REDIRECT_URI
    
    if not client_id or not redirect_uri:
        return jsonify({"error": "Google OAuth is not configured on the server."}), 503
        
    scopes = [
        "https://www.googleapis.com/auth/gmail.send",
        "https://www.googleapis.com/auth/gmail.readonly"
    ]
    
    auth_url = "https://accounts.google.com/o/oauth2/v2/auth"
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(scopes),
        "access_type": "offline",
        "prompt": "consent",
        "state": user_id  # Pass user_id to retrieve it in the callback
    }
    
    url = f"{auth_url}?{urllib.parse.urlencode(params)}"
    return jsonify({"auth_url": url})


@fuse_bp.route("/integration/gmail/callback", methods=["GET"])
def gmail_oauth_callback():
    """GET /fuse/integration/gmail/callback — handles Google OAuth redirect."""
    error = request.args.get("error")
    if error:
        return f"OAuth Error: {error}", 400
        
    code = request.args.get("code")
    user_id = request.args.get("state")  # We passed user_id in the state param
    
    if not code or not user_id:
        return "Missing code or state parameter", 400
        
    token_url = "https://oauth2.googleapis.com/token"
    data = {
        "code": code,
        "client_id": CONFIG.GOOGLE_OAUTH_CLIENT_ID,
        "client_secret": CONFIG.GOOGLE_OAUTH_CLIENT_SECRET,
        "redirect_uri": CONFIG.GOOGLE_OAUTH_REDIRECT_URI,
        "grant_type": "authorization_code"
    }
    
    response = requests.post(token_url, data=data)
    if response.status_code != 200:
        return f"Failed to get tokens: {response.text}", 400
        
    token_data = response.json()
    
    # Calculate expiry time
    expires_in = token_data.get("expires_in", 3600)
    expires_at = (datetime.utcnow() + timedelta(seconds=expires_in)).isoformat() + "Z"
    
    tokens = {
        "access_token": token_data.get("access_token"),
        "refresh_token": token_data.get("refresh_token"),
        "expires_at": expires_at
    }
    
    # Save tokens to database
    db.integration.save_integration_tokens(user_id, "gmail", tokens)
        
    return redirect(f"{CONFIG.FRONTEND_URL}/fuse/integrations")


@fuse_bp.route("/integration/<integration_id>", methods=["DELETE"])
@require_auth
def revoke_integration(integration_id):
    """DELETE /fuse/integration/<id> — revokes an integration."""
    user_id = request.user["uid"]
    
    # Actually delete from db
    success = db.integration.delete_integration(user_id, integration_id)
    if not success:
        return jsonify({"error": "Integration not found or already removed"}), 404
        
    # If it's a google oauth integration, you could optionally call google's revoke endpoint here
    # requests.post("https://oauth2.googleapis.com/revoke", params={"token": token})
    
    return jsonify({"success": True})


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


# ─── Runs & Logs ──────────────────────────────────────────────────────────────

@fuse_bp.route("/workflows/<workflow_id>/runs", methods=["GET"])
@require_auth
def list_workflow_runs(workflow_id):
    """
    GET /fuse/workflows/:id/runs
    ─────────────────────────────
    Return the trigger history for a workflow, newest first.

    Query params:
        limit            (int, default 20, max 100)
        after_started_at (str ISO-8601)  ─ cursor from previous page
        after_run_id     (str)           ┘
    """
    owner_id = request.user["uid"]

    workflow = db.workflow.get(workflow_id, owner_id)
    if workflow is None:
        return jsonify({"error": "Workflow not found"}), 404

    try:
        limit = min(int(request.args.get("limit", 20)), 100)
    except (ValueError, TypeError):
        limit = 20

    after_started_at = request.args.get("after_started_at") or None
    after_run_id     = request.args.get("after_run_id") or None

    result = db.workflow_run.list_runs_for_workflow(
        workflow_id,
        owner_id,
        limit=limit,
        after_started_at=after_started_at,
        after_run_id=after_run_id,
    )
    return jsonify(result)


@fuse_bp.route("/runs/<run_id>", methods=["GET"])
@require_auth
def get_run(run_id):
    """
    GET /fuse/runs/:run_id
    ───────────────────────
    Return a single run document.
    """
    owner_id = request.user["uid"]
    run = db.workflow_run.get_run(run_id, owner_id)
    if run is None:
        return jsonify({"error": "Run not found"}), 404
    return jsonify(run)


@fuse_bp.route("/runs/<run_id>/logs", methods=["GET"])
@require_auth
def get_run_logs(run_id):
    """
    GET /fuse/runs/:run_id/logs
    ────────────────────────────
    Return the per-node execution logs for a run, ordered by start time.

    Query params:
        limit            (int, default 25, max 100)
        after_started_at (str ISO-8601)  \u2500 cursor from previous page
        after_log_id     (str)           ┘
    """
    owner_id = request.user["uid"]

    run = db.workflow_run.get_run(run_id, owner_id)
    if run is None:
        return jsonify({"error": "Run not found"}), 404

    try:
        limit = min(int(request.args.get("limit", 25)), 100)
    except (ValueError, TypeError):
        limit = 25

    after_started_at = request.args.get("after_started_at") or None
    after_log_id     = request.args.get("after_log_id") or None

    result = db.workflow_run.list_logs_for_run(
        run_id,
        owner_id,
        limit=limit,
        after_started_at=after_started_at,
        after_log_id=after_log_id,
    )
    return jsonify(result)


# ─── Compiled graph versions ──────────────────────────────────────────────────

@fuse_bp.route("/workflows/<workflow_id>/versions", methods=["GET"])
@require_auth
def list_workflow_versions(workflow_id):
    """
    GET /fuse/workflows/:id/versions
    ──────────────────────────────────
    Return all compiled graph versions for a workflow, newest first.
    """
    owner_id = request.user["uid"]

    workflow = db.workflow.get(workflow_id, owner_id)
    if workflow is None:
        return jsonify({"error": "Workflow not found"}), 404

    versions = db.workflow_version.list_for_workflow(workflow_id, owner_id)
    # Strip the compiled_graph dict from the list response to keep it lightweight;
    # callers that need the full graph can fetch /versions/:version_id directly.
    slim = [
        {k: v for k, v in ver.items() if k != "compiled_graph"}
        for ver in versions
    ]
    return jsonify(slim)


@fuse_bp.route("/versions/<version_id>", methods=["GET"])
@require_auth
def get_version(version_id):
    """
    GET /fuse/versions/:version_id
    ────────────────────────────────
    Return a single compiled graph version (including the full compiled_graph).
    """
    owner_id = request.user["uid"]
    version  = db.workflow_version.get(version_id)
    if version is None:
        return jsonify({"error": "Version not found"}), 404
    if version.get("owner_id") != owner_id:
        return jsonify({"error": "Version not found"}), 404
    return jsonify(version)
