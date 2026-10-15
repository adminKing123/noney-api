from flask import Blueprint, request, jsonify
from middleware.auth import require_auth
from db import db
from fuse.compiler import compile_workflow_graph
from fuse.runtime import runtime
from fuse.workflow_generator import generate_workflow_from_prompt
from config import CONFIG
from fuse.executor import run_workflow_async
from fuse.nodes.webhook import verify_webhook_request
from datetime import datetime

bp = Blueprint("fuse_workflows", __name__)


def _teardown_webhooks(workflow: dict) -> None:
    """Delete the Webhooks for workflow, if registered."""
    from utils.integrations.webex_utils import cleanup_webex_workflow_webhook
    from utils.integrations.github_utils import cleanup_github_workflow_webhook

    owner_id = workflow.get("owner_id", "")
    compiled_graph = workflow.get("compiled_graph") or {}
    
    starter_type = compiled_graph.get("starter", {}).get("node_type")
    
    if starter_type == "webex_message":
        cleanup_webex_workflow_webhook(owner_id, compiled_graph)
    elif starter_type == "github_pull_request":
        cleanup_github_workflow_webhook(owner_id, compiled_graph)

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


@bp.route("/workflows/generate", methods=["POST"])
@require_auth
def generate_workflow():
    """
    POST /fuse/workflows/generate
    ─────────────────────────────
    Create a workflow from a natural-language prompt using AI.

    Body: { "prompt": "Send me a notification every Monday at 8am" }

    Response (201): full workflow document with generated nodes/edges.
    Response (400): { "success": false, "errors": [...] }
    """
    owner_id = request.user["uid"]
    prompt = ((request.json or {}).get("prompt") or "").strip()

    if not prompt:
        return jsonify({"error": "prompt is required"}), 400

    user_integrations = db.integration.get_all_integrations(owner_id)
    result = generate_workflow_from_prompt(
        prompt,
        user_integrations,
        owner_id=owner_id,
    )

    if not result.get("success"):
        return jsonify({"success": False, "errors": result.get("errors") or []}), 400

    workflow = db.workflow.create(owner_id=owner_id, name=result["name"])
    updated = db.workflow.update_graph(
        workflow["id"],
        owner_id,
        result["nodes"],
        result["edges"],
    )
    return jsonify(updated), 201


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
    """
    PATCH /fuse/workflows/:id/graph — save the React Flow node/edge graph.

    Body:
        nodes  – workflow logic nodes only  (fuse_node type)
        edges  – workflow edges
        blocks – optional; purely-visual block overlays (fuse_block type).
                 Stored separately and never passed to the compiler.
    """
    owner_id = request.user["uid"]
    body   = request.json or {}
    nodes  = body.get("nodes",  [])
    edges  = body.get("edges",  [])
    blocks = body.get("blocks") # None if key absent → db layer skips update
    updated = db.workflow.update_graph(workflow_id, owner_id, nodes, edges, blocks)
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

    # WebexMessageExecution.start() may attach webhook metadata to compiled_graph.
    compiled_graph = runtime.get_execution(workflow_id).compiled_graph  # type: ignore[union-attr]

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

    _teardown_webhooks(workflow)
    runtime.deactivate(workflow_id)
    
    starter_type = (workflow.get("compiled_graph") or {}).get("starter", {}).get("node_type")
    if starter_type == "webex_message":
        db.workflow.clear_compiled_webex_webhook(workflow_id, owner_id)
    # For Github we pop it in runtime.deactivate already but we can also do it in DB
    if starter_type == "github_pull_request":
        compiled = workflow.get("compiled_graph") or {}
        if "github_webhook" in compiled:
            compiled.pop("github_webhook")
            db.workflow.save_compilation(workflow_id, owner_id, compiled, compiled.get("graph_hash"), compiled.get("compiled_at"))
    updated = db.workflow.update_status(workflow_id, owner_id, "inactive")
    return jsonify({"success": True, "workflow": updated})


@bp.route("/workflows/<workflow_id>", methods=["DELETE"])
@require_auth
def delete_workflow(workflow_id):
    """DELETE /fuse/workflows/:id — permanently remove a workflow."""
    owner_id = request.user["uid"]
    workflow = db.workflow.get(workflow_id, owner_id)
    if workflow is None:
        return jsonify({"error": "Workflow not found"}), 404

    # Always delete the webhooks from the API using persisted metadata —
    # runtime.deactivate alone is not enough when the workflow is inactive or
    # the server was restarted since activation.
    _teardown_webhooks(workflow)
    runtime.deactivate(workflow_id)

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
    execution = runtime.resolve_execution(workflow_id)
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


# ─── Webex message webhook trigger ────────────────────────────────────────────

# ─── GitHub webhook trigger ───────────────────────────────────────────────────

@bp.route("/github/webhook/<workflow_id>", methods=["POST"])
def trigger_github_webhook(workflow_id):
    execution = runtime.resolve_execution(workflow_id)
    if execution is None:
        return jsonify({"error": "Workflow not found or not active."}), 404

    compiled_graph = execution.compiled_graph
    starter = compiled_graph.get("starter", {})

    if starter.get("node_type") != "github_pull_request":
        return jsonify({"error": "This workflow is not GitHub-triggered."}), 400

    body_bytes = request.get_data()
    signature = request.headers.get("X-Hub-Signature-256", "")
    webhook_meta = compiled_graph.get("github_webhook") or {}
    secret = webhook_meta.get("secret", "")

    from utils.integrations.github_utils import (
        normalise_github_pr_event,
        verify_github_webhook_signature,
    )

    if secret and not verify_github_webhook_signature(body_bytes, signature, secret):
        return jsonify({"error": "Invalid GitHub webhook signature."}), 401

    try:
        event_payload = request.get_json(force=True, silent=True) or {}
    except Exception:
        event_payload = {}

    event_type = request.headers.get("X-GitHub-Event", "")
    
    starter_config = starter.get("config", {})
    trigger_data = normalise_github_pr_event(
        event_payload,
        event_type,
        starter_config,
    )

    if trigger_data is None:
        return jsonify({"status": "ignored"}), 200

    run_workflow_async(compiled_graph, trigger_data, trigger_type="github_pull_request")
    return jsonify({"status": "accepted", "workflow_id": workflow_id}), 202

@bp.route("/webex/webhook/<workflow_id>", methods=["POST"])
def trigger_webex_message(workflow_id):
    """
    /fuse/webex/webhook/<workflow_id>
    ─────────────────────────────────
    Public endpoint registered with Webex when a webex_message workflow is active.

    Webex sends a lightweight event payload; we fetch the full message, apply
    starter filters, then run the workflow asynchronously.
    """
    execution = runtime.resolve_execution(workflow_id)
    if execution is None:
        return jsonify({"error": "Workflow not found or not active."}), 404

    compiled_graph = execution.compiled_graph
    starter = compiled_graph.get("starter", {})

    if starter.get("node_type") != "webex_message":
        return jsonify({"error": "This workflow is not Webex message-triggered."}), 400

    body_bytes = request.get_data()
    signature = request.headers.get("X-Spark-Signature", "")
    webhook_meta = compiled_graph.get("webex_webhook") or {}
    secret = webhook_meta.get("secret", "")

    from utils.integrations.webex_utils import (
        get_webex_access_token,
        get_webex_own_person_id,
        normalise_webex_message_event,
        verify_webex_webhook_signature,
    )

    if secret:
        if not signature:
            logger.warning(
                "[FUSE] Webex webhook 401 — missing X-Spark-Signature "
                "(workflow=%s, body_bytes=%d)",
                workflow_id,
                len(body_bytes),
            )
            return jsonify({"error": "Missing Webex webhook signature."}), 401
        if not verify_webex_webhook_signature(body_bytes, signature, secret):
            logger.warning(
                "[FUSE] Webex webhook 401 — signature mismatch "
                "(workflow=%s, stored_webhook=%s, body_bytes=%d). "
                "Often caused by an old duplicate Webex webhook still pointing "
                "at this URL — deactivate/reactivate the workflow or remove "
                "extra webhooks in Webex.",
                workflow_id,
                webhook_meta.get("id"),
                len(body_bytes),
            )
            return jsonify({"error": "Invalid Webex webhook signature."}), 401

    try:
        event_payload = request.get_json(force=True, silent=True) or {}
    except Exception:
        event_payload = {}

    owner_id = compiled_graph.get("owner_id", "")
    access_token = get_webex_access_token(owner_id)
    if not access_token:
        return jsonify({"error": "Webex integration unavailable."}), 503

    starter_config = starter.get("config", {})
    own_person_id = get_webex_own_person_id(access_token)

    trigger_data = normalise_webex_message_event(
        access_token,
        event_payload,
        starter_config,
        own_person_id=own_person_id,
    )

    if trigger_data is None:
        return jsonify({"status": "ignored"}), 200

    run_workflow_async(compiled_graph, trigger_data, trigger_type="webex_message")
    return jsonify({"status": "accepted", "workflow_id": workflow_id}), 202