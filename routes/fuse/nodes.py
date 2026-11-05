from flask import Blueprint, jsonify, request
from middleware.auth import require_auth
from fuse.node_catalog_browse import (
    list_catalog_sections,
    list_nodes_in_section,
    search_catalog_listings,
)
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


@bp.route("/nodes/catalog/sections", methods=["GET"])
@require_auth
def get_catalog_sections():
    """
    GET /fuse/nodes/catalog/sections?role=starter|action
    Section list for n8n-style picker (counts only — no node payloads).
    """
    role = (request.args.get("role") or "action").strip().lower()
    if role not in ("starter", "action"):
        return jsonify({"error": "Query param 'role' must be 'starter' or 'action'."}), 400
    user_id = request.user["uid"]
    sections = list_catalog_sections(role, _user_integrations(user_id))
    return jsonify({"role": role, "sections": sections})


@bp.route("/nodes/catalog/nodes", methods=["GET"])
@require_auth
def get_catalog_section_nodes():
    """
    GET /fuse/nodes/catalog/nodes?role=action&section=Google&limit=&offset=
    Lazy-load listing metadata for one section.
    """
    role = (request.args.get("role") or "action").strip().lower()
    section = request.args.get("section")
    if role not in ("starter", "action"):
        return jsonify({"error": "Query param 'role' must be 'starter' or 'action'."}), 400
    if not section or not str(section).strip():
        return jsonify({"error": "Query param 'section' is required."}), 400
    try:
        limit = min(int(request.args.get("limit", 200)), 500)
        offset = max(int(request.args.get("offset", 0)), 0)
    except ValueError:
        return jsonify({"error": "limit and offset must be integers."}), 400

    user_id = request.user["uid"]
    payload = list_nodes_in_section(
        role,
        section,
        _user_integrations(user_id),
        limit=limit,
        offset=offset,
    )
    return jsonify(payload)


@bp.route("/nodes/catalog/search", methods=["GET"])
@require_auth
def get_catalog_search():
    """
    GET /fuse/nodes/catalog/search?q=&role=starter|action&limit=
    Search listing metadata for the picker (does not load full catalog).
    """
    query = (request.args.get("q") or request.args.get("query") or "").strip()
    role_param = (request.args.get("role") or "").strip().lower()
    role = role_param if role_param in ("starter", "action") else None
    try:
        limit = min(int(request.args.get("limit", 40)), 100)
    except ValueError:
        return jsonify({"error": "limit must be an integer."}), 400

    user_id = request.user["uid"]
    results = search_catalog_listings(
        query,
        _user_integrations(user_id),
        role=role,
        limit=limit,
    )
    return jsonify({"query": query, "role": role, "results": results})


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
    return jsonify({
        "variables": [
            {"token": "system.workflow_id", "label": "Workflow ID", "group": "Metadata"},
            {"token": "system.run_id", "label": "Execution Run ID", "group": "Metadata"},
            {"token": "system.triggered_at", "label": "Triggered At", "group": "Metadata"},
            {"token": "system.trigger_type", "label": "Trigger Type", "group": "Metadata"},
        ],
    })


@bp.route("/nodes/schedule-timezones", methods=["GET"])
@require_auth
def get_schedule_timezones():
    """GET /fuse/nodes/schedule-timezones — cron-job.org allowed IANA time zones."""
    from fuse.schedule_timezones import load_schedule_timezones

    zones = load_schedule_timezones()
    return jsonify({"count": len(zones), "timezones": zones})


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
