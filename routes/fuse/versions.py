from flask import Blueprint, jsonify
from middleware.auth import require_auth
from db import db

bp = Blueprint("fuse_versions", __name__)

# ─── Compiled graph versions ──────────────────────────────────────────────────

@bp.route("/workflows/<workflow_id>/versions", methods=["GET"])
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


@bp.route("/versions/<version_id>", methods=["GET"])
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
