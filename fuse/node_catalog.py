"""
fuse/node_catalog.py — extended with search + on-demand detail serialization.
"""

from __future__ import annotations

import re
from typing import Any, Iterator

from fuse.compiler import _REQUIRED_FIELDS
from fuse.node_definitions import ACTION_NODES, STARTER_NODES

BUILDER_FIELD_TYPES = frozenset({
    "body_builder",
    "condition_builder",
    "json_value_builder",
    "key_value_builder",
})

BUILDER_FORMAT_HINTS: dict[str, str] = {
    "body_builder": (
        '{"mode": "visual", "rootType": "object|array|string|number|boolean", '
        '"fields": [{"key": "field_name", "type": "string|number|boolean|array|object", '
        '"items": {"type": "..."}, "fields": [...]}], '
        '"items": {"type": "string|number|boolean|array|object", "fields": [...]}}'
    ),
    "condition_builder": (
        '{"combinator": "and|or", "conditions": [{"variable": "{{ref.field}}", "operator": "is", "value": "..."}]}'
    ),
    "json_value_builder": (
        '{"mode": "visual", "rootType": "object|array|string|number|boolean", '
        '"fields": [{"key": "...", "type": "string", "value": "..."}], '
        '"elements": [...], "value": "..."}'
    ),
    "key_value_builder": (
        '{"mode": "visual", "fields": [{"key": "...", "type": "string", "value": "..."}]}'
    ),
}


def get_available_nodes(user_integrations: dict | None) -> dict[str, list[dict]]:
    user_integrations = user_integrations or {}
    starters: list[dict] = []
    actions: list[dict] = []

    for node in STARTER_NODES:
        required = node.get("required_integration")
        if required:
            integration = user_integrations.get(required) or {}
            if not integration.get("configured"):
                continue
        starters.append(node)

    for node in ACTION_NODES:
        required = node.get("required_integration")
        if required:
            integration = user_integrations.get(required) or {}
            if not integration.get("configured"):
                continue
        actions.append(node)

    return {"starters": starters, "actions": actions}


def iter_all_nodes(catalog: dict[str, list[dict]]) -> Iterator[tuple[dict, str]]:
    for starter in catalog.get("starters") or []:
        yield starter, "starter"
    for action in catalog.get("actions") or []:
        yield action, "action"


def iter_config_fields(node_def: dict) -> Iterator[dict]:
    form = node_def.get("config_form") or {}
    for section in form.get("sections") or []:
        for field in section.get("fields") or []:
            yield field


def build_schema_key_map(catalog: dict[str, list[dict]]) -> dict[str, str]:
    """Map node_type -> body_builder config key (derived from config_form)."""
    mapping: dict[str, str] = {}
    for node_def, _role in iter_all_nodes(catalog):
        for field in iter_config_fields(node_def):
            if field.get("type") == "body_builder":
                mapping[node_def["type"]] = field["key"]
                break
    return mapping


def _tokenize(text: str) -> list[str]:
    return re.findall(r"[a-z0-9_]+", (text or "").lower())


def _node_search_text(node: dict, role: str) -> str:
    parts = [
        node.get("type", ""),
        node.get("label", ""),
        node.get("description", ""),
        node.get("section", ""),
        role,
    ]
    for field in iter_config_fields(node):
        parts.append(field.get("key") or "")
        parts.append(field.get("label") or "")
    return " ".join(parts).lower()


def search_nodes(
    catalog: dict[str, list[dict]],
    query: str,
    *,
    role: str | None = None,
    limit: int = 15,
) -> list[dict]:
    """
    Keyword search over the node catalog. Returns compact entries only.
    """
    tokens = _tokenize(query)
    query_norm = query.lower().strip().replace(" ", "_")
    scored: list[tuple[float, dict, str]] = []

    for node, node_role in iter_all_nodes(catalog):
        if role and node_role != role:
            continue

        blob = _node_search_text(node, node_role)
        score = 0.0

        if query_norm and query_norm == node.get("type", ""):
            score += 100
        if query_norm and query_norm in blob.replace(" ", "_"):
            score += 20

        for token in tokens:
            if len(token) < 2:
                continue
            if token in blob:
                score += 2
            if token in (node.get("type") or ""):
                score += 5

        if score > 0 or not tokens:
            scored.append((score, node, node_role))

    scored.sort(key=lambda x: (-x[0], x[1].get("label", "")))
    top = scored[:limit] if tokens else scored[:limit]

    return [
        {
            "node_type":   node["type"],
            "label":       node.get("label"),
            "role":        node_role,
            "section":     node.get("section"),
            "description": node.get("description", ""),
            "match_score": score,
        }
        for score, node, node_role in top
    ]


def _serialize_fields(fields: list[dict], depth: int = 0) -> list[dict]:
    if depth > 6:
        return []
    out: list[dict] = []
    for field in fields or []:
        entry: dict[str, Any] = {
            "key":      field.get("key"),
            "label":    field.get("label"),
            "type":     field.get("type"),
            "required": bool(field.get("required")),
        }
        if field.get("hint"):
            entry["hint"] = field["hint"]
        if field.get("placeholder"):
            entry["placeholder"] = field["placeholder"]
        if field.get("options"):
            entry["options"] = [
                {"label": o.get("label"), "value": o.get("value")}
                for o in field["options"]
            ]
        if field.get("showDescription"):
            entry["showDescription"] = True
        if field.get("showEnum"):
            entry["showEnum"] = True
        if field.get("type") in BUILDER_FIELD_TYPES:
            entry["value_format"] = BUILDER_FORMAT_HINTS.get(field["type"], "")
        out.append(entry)
    return out


def _serialize_config_form(config_form: dict | None) -> dict:
    form = config_form or {}
    sections = []
    for section in form.get("sections") or []:
        sections.append({
            "title":  section.get("title"),
            "layout": section.get("layout"),
            "fields": _serialize_fields(section.get("fields") or []),
        })
    return {"presets": form.get("presets") or [], "sections": sections}


def serialize_node_detail(node: dict, role: str) -> dict:
    """Full node specification for workflow generation."""
    node_type = node["type"]
    required = [
        k for k in (_REQUIRED_FIELDS.get(node_type) or [])
    ]
    # Also mark required fields from config_form
    for field in iter_config_fields(node):
        if field.get("required") and field.get("key"):
            if field["key"] not in required:
                required.append(field["key"])

    entry: dict[str, Any] = {
        "node_type":       node_type,
        "label":           node.get("label"),
        "role":            role,
        "section":         node.get("section"),
        "description":     node.get("description", ""),
        "required_fields": required,
        "defaults":        node.get("defaults") or {},
        "config_form":     _serialize_config_form(node.get("config_form")),
        "presets":         (node.get("config_form") or {}).get("presets") or [],
    }

    branch_handles = node.get("branch_handles")
    if branch_handles:
        entry["branch_handles"] = branch_handles
        entry["rules"] = [
            "Connect each branch handle to at most one outgoing edge.",
            f"Use source_handle values: {', '.join(branch_handles)} for outgoing edges from this node.",
        ]

    if role == "starter":
        entry["rules"] = (entry.get("rules") or []) + [
            "Exactly one starter node per workflow.",
            "Set isStarter=true on this node in the plan.",
        ]

    return entry


def get_node_details(
    catalog: dict[str, list[dict]],
    node_types: list[str],
) -> tuple[list[dict], list[str]]:
    """Return full details for requested types; list any not found."""
    type_map: dict[str, tuple[dict, str]] = {}
    for node, role in iter_all_nodes(catalog):
        type_map[node["type"]] = (node, role)

    details: list[dict] = []
    missing: list[str] = []
    for nt in node_types:
        if nt in type_map:
            node, role = type_map[nt]
            details.append(serialize_node_detail(node, role))
        else:
            missing.append(nt)
    return details, missing


def lookup_node_def(catalog: dict[str, list[dict]], node_type: str) -> dict | None:
    for starter in catalog.get("starters") or []:
        if starter["type"] == node_type:
            return starter
    for action in catalog.get("actions") or []:
        if action["type"] == node_type:
            return action
    return None


# Legacy helper — prefer search + get_node_details for AI generation.
def serialize_catalog_for_ai(catalog: dict[str, list[dict]]) -> list[dict]:
    return [
        serialize_node_detail(node, role)
        for node, role in iter_all_nodes(catalog)
    ]
