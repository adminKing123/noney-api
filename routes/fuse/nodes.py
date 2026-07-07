from flask import Blueprint, jsonify, request
from middleware.auth import require_auth
from fuse.node_definitions import ACTION_NODES, STARTER_NODES
from db import db

bp = Blueprint("fuse_nodes", __name__)


@bp.route("/nodes/starter", methods=["GET"])
@require_auth
def get_starter_nodes():
    """GET /fuse/nodes/starter — returns starter node definitions. Integration-gated starters require configuration."""
    user_id = request.user["uid"]
    user_integrations = db.integration.get_all_integrations(user_id)

    filtered_nodes = []
    for node in STARTER_NODES:
        required_integration = node.get("required_integration")
        if required_integration:
            integration_data = user_integrations.get(required_integration)
            if not integration_data or not integration_data.get("configured"):
                continue
        filtered_nodes.append(node)

    return jsonify(filtered_nodes)


@bp.route("/nodes/actions", methods=["GET"])
@require_auth
def get_action_nodes():
    """GET /fuse/nodes/actions — returns action node definitions. Only returns nodes requiring integrations if they are configured."""
    user_id = request.user["uid"]
    user_integrations = db.integration.get_all_integrations(user_id)

    filtered_nodes = []
    for node in ACTION_NODES:
        required_integration = node.get("required_integration")
        if required_integration:
            integration_data = user_integrations.get(required_integration)
            if not integration_data or not integration_data.get("configured"):
                continue
        filtered_nodes.append(node)

    return jsonify(filtered_nodes)

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
