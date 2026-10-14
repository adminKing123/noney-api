from flask import Blueprint, request, jsonify
from config import get_fuse_run_ws_public_base
from middleware.auth import require_auth
from db import db

bp = Blueprint("fuse_runs", __name__)

# ─── Runs & Logs ──────────────────────────────────────────────────────────────

@bp.route("/workflows/<workflow_id>/runs", methods=["GET"])
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


@bp.route("/runs/<run_id>", methods=["GET"])
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


@bp.route("/runs/<run_id>/logs", methods=["GET"])
@require_auth
def get_run_logs(run_id):
    """
    GET /fuse/runs/:run_id/logs
    ────────────────────────────
    Return the per-node execution logs for a run, ordered by start time.

    Query params:
        limit            (int, default 25, max 100)
        after_started_at (str ISO-8601)  — cursor from previous page
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


@bp.route("/runs/<run_id>/live-config", methods=["GET"])
@require_auth
def run_live_config(run_id):
    """
    GET /fuse/runs/:run_id/live-config
    ───────────────────────────────────
    WebSocket URL for streaming run + node execution updates.
    """
    owner_id = request.user["uid"]
    run = db.workflow_run.get_run(run_id, owner_id)
    if run is None:
        return jsonify({"error": "Run not found"}), 404

    base = get_fuse_run_ws_public_base()
    return jsonify({"ws_url": f"{base}/fuse/runs/live"})
