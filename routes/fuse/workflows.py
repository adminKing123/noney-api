from flask import Blueprint, request, jsonify
from middleware.auth import require_auth
from db import db
from fuse.compiler import compile_workflow_graph
from fuse.runtime import runtime
from config import CONFIG
from fuse.executor import run_workflow_async
from fuse.nodes.webhook import verify_webhook_request
from datetime import datetime

bp = Blueprint("fuse_workflows", __name__)

# ─── Workflows ────────────────────────────────────────────────────────────────

@bp.route("/workflows", methods=["GET"])
@require_auth
def list_workflows():
    """
    GET /fuse/workflows
    ────────────────────
    List workflows owned by the authenticated user, newest first.

    Query params:
        limit           (int, default 20, max 100)
        after_created_at (str ISO-8601)  — cursor from previous page
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

@bp.route("/discover", methods=["GET"])
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


@bp.route("/workflows", methods=["POST"])
@require_auth
def create_workflow():
    """POST /fuse/workflows — create a new workflow for the authenticated user."""
    owner_id = request.user["uid"]
    name = (request.json or {}).get("name", "Untitled Workflow").strip() or "Untitled Workflow"
    workflow = db.workflow.create(owner_id=owner_id, name=name)
    return jsonify(workflow), 201


@bp.route("/workflows/<workflow_id>", methods=["GET"])
@require_auth
def get_workflow(workflow_id):
    """GET /fuse/workflows/:id — fetch a single workflow by ID."""
    owner_id = request.user["uid"]
    workflow = db.workflow.get(workflow_id, owner_id)
    if workflow is None:
        return jsonify({"error": "Workflow not found"}), 404
    return jsonify(workflow)


@bp.route("/workflows/<workflow_id>/name", methods=["PATCH"])
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


@bp.route("/workflows/<workflow_id>/graph", methods=["PATCH"])
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


@bp.route("/workflows/<workflow_id>/status", methods=["PATCH"])
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


@bp.route("/workflows/<workflow_id>/activate", methods=["POST"])
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


@bp.route("/workflows/<workflow_id>/deactivate", methods=["POST"])
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


@bp.route("/workflows/<workflow_id>", methods=["DELETE"])
@require_auth
def delete_workflow(workflow_id):
    """DELETE /fuse/workflows/:id — permanently remove a workflow."""
    owner_id = request.user["uid"]
    success = db.workflow.delete(workflow_id, owner_id)
    if not success:
        return jsonify({"error": "Workflow not found"}), 404
    return jsonify({"success": True, "id": workflow_id})


# ─── Public webhook trigger ───────────────────────────────────────────────────

@bp.route(
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
