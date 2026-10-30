"""
fuse/node_listing.py
====================
Listing metadata vs full definitions for Fuse node catalog API.
"""

from __future__ import annotations

from fuse.node_definitions import ACTION_NODES, STARTER_NODES

NODE_LISTING_KEYS = (
    "type",
    "label",
    "icon",
    "section",
    "description",
)


def node_to_listing_metadata(node: dict) -> dict:
    """Fields needed for picker/search UI — excludes config_form and defaults."""
    return {k: node[k] for k in NODE_LISTING_KEYS if k in node}


def node_available_for_user(node: dict, user_integrations: dict) -> bool:
    required = node.get("required_integration")
    if not required:
        return True
    integration_data = user_integrations.get(required)
    return bool(integration_data and integration_data.get("configured"))


def filter_nodes_for_user(nodes: list[dict], user_integrations: dict) -> list[dict]:
    return [n for n in nodes if node_available_for_user(n, user_integrations)]


def find_node_definition(node_type: str) -> dict | None:
    for node in (*STARTER_NODES, *ACTION_NODES):
        if node.get("type") == node_type:
            return node
    return None


