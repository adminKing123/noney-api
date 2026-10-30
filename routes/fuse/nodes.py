from flask import Blueprint, jsonify, request
from middleware.auth import require_auth
from fuse.node_definitions import ACTION_NODES, STARTER_NODES
from fuse.node_listing import (
    filter_nodes_for_user,
    find_node_definition,
    node_available_for_user,
    node_to_listing_metadata,
)
from db import db

bp = Blueprint("fuse_nodes", __name__)


def _user_integrations(user_id: str) -> dict:
    return db.integration.get_all_integrations(user_id)


@bp.route("/nodes/starter", methods=["GET"])
@require_auth
def get_starter_nodes():
    """GET /fuse/nodes/starter — listing metadata for starter nodes (no config_form)."""
    user_id = request.user["uid"]
    filtered = filter_nodes_for_user(STARTER_NODES, _user_integrations(user_id))
    return jsonify([node_to_listing_metadata(n) for n in filtered])


@bp.route("/nodes/actions", methods=["GET"])
@require_auth
def get_action_nodes():
    """GET /fuse/nodes/actions — listing metadata for action nodes (no config_form)."""
    user_id = request.user["uid"]
    filtered = filter_nodes_for_user(ACTION_NODES, _user_integrations(user_id))
    return jsonify([node_to_listing_metadata(n) for n in filtered])


@bp.route("/nodes/system-variables", methods=["GET"])
@require_auth
def get_system_variables():
    """GET /fuse/nodes/system-variables — returns available runtime system variables."""
    import pytz
    timezones = list(pytz.common_timezones)

    return jsonify({
        "variables": [
            {"token": "system.workflow_id", "label": "Workflow ID", "group": "Metadata"},
            {"token": "system.run_id", "label": "Execution Run ID", "group": "Metadata"},
            {"token": "system.triggered_at", "label": "Triggered At", "group": "Metadata"},
            {"token": "system.trigger_type", "label": "Trigger Type", "group": "Metadata"},
        ],
        "timezones": timezones
    })


@bp.route("/nodes/<node_type>", methods=["GET"])
@require_auth
def get_node_definition(node_type: str):
    """GET /fuse/nodes/<node_type> — full definition including config_form and defaults."""
    node = find_node_definition(node_type)
    if not node:
        return jsonify({"error": f"Unknown node type '{node_type}'."}), 404

    user_id = request.user["uid"]
    if not node_available_for_user(node, _user_integrations(user_id)):
        return jsonify({"error": "This node requires an integration that is not configured."}), 403

    return jsonify(node)
