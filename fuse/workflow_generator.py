"""
fuse/workflow_generator.py
==========================
Turn a natural-language prompt into a valid React Flow workflow graph using AI.

Uses a two-phase agent:
  1. Tool discovery — search_fuse_nodes + get_fuse_node_details (scalable to 1000s of nodes)
  2. Structured output — generate workflow plan from fetched node specs only
"""

from __future__ import annotations

import json
import uuid
from typing import Any

from pydantic import BaseModel, Field

from ai import AIProvider
from config import CONFIG
from fuse.compiler import _REQUIRED_FIELDS, compile_workflow_graph
from fuse.node_catalog import (
    build_schema_key_map,
    get_available_nodes,
    lookup_node_def,
)
from fuse.schema_utils import (
    apply_user_prompt_hints,
    build_prompt_extras,
    enrich_plan_node_configs,
    normalize_node_schemas,
)
from fuse.workflow_agent import build_generation_messages, run_discovery_phase
from fuse.workflow_tools import get_fetched_node_types


# ─── Pydantic schema for AI structured output ─────────────────────────────────

class GeneratedEdge(BaseModel):
    source:        str = Field(description="Source node ref (e.g. starter, step_1)")
    target:        str = Field(description="Target node ref")
    source_handle: str = Field(
        default="default",
        description="Edge handle: default, true, false, case_0… (switch), item/done (for_each)",
    )


class GeneratedNode(BaseModel):
    ref:       str = Field(description="Unique logical reference within this workflow")
    node_type: str = Field(description="Must match a node_type from get_fuse_node_details")
    label:     str = Field(description="Short display label for the node")
    config:    dict[str, Any] = Field(
        default_factory=dict,
        description="Node configuration keyed by config_form field keys",
    )


class GeneratedWorkflowPlan(BaseModel):
    name:  str = Field(description="Short workflow title, under 80 characters")
    nodes: list[GeneratedNode] = Field(min_length=1)
    edges: list[GeneratedEdge] = Field(default_factory=list)


# ─── Graph conversion ─────────────────────────────────────────────────────────

_STARTER_X = 250
_STARTER_Y = 120
_H_SPACING = 320
_V_BRANCH  = 140


def _apply_defaults(node_type: str, config: dict, node_def: dict | None) -> dict:
    """Merge AI config with defaults from node definition presets/defaults."""
    config = dict(config or {})
    node_def = node_def or {}
    form = node_def.get("config_form") or {}

    for key, val in (node_def.get("defaults") or {}).items():
        config.setdefault(key, val)

    presets = form.get("presets") or []
    if presets and not any(config.get(k) for k in (_REQUIRED_FIELDS.get(node_type) or [])):
        for key, val in (presets[0].get("values") or {}).items():
            config.setdefault(key, val)

    from fuse.node_catalog import BUILDER_FIELD_TYPES, iter_config_fields

    for field in iter_config_fields(node_def):
        ftype = field.get("type")
        fkey = field.get("key")
        if not fkey or config.get(fkey):
            continue
        if ftype == "condition_builder":
            config[fkey] = {
                "combinator": "and",
                "conditions": [{"variable": "", "operator": "is", "value": ""}],
            }
        elif ftype in ("json_value_builder", "key_value_builder"):
            config[fkey] = {"mode": "visual", "rootType": "object", "fields": []}
        elif ftype == "body_builder":
            config[fkey] = {"mode": "visual", "rootType": "object", "fields": []}
        elif ftype == "select" and field.get("options"):
            config[fkey] = field["options"][0].get("value")

    return config


def _resolve_variables_in_config(config: Any, ref_to_id: dict[str, str]) -> Any:
    if isinstance(config, str):
        out = config
        for ref, node_id in ref_to_id.items():
            out = out.replace(f"{{{{{ref}.", f"{{{{{node_id}.")
        return out
    if isinstance(config, list):
        return [_resolve_variables_in_config(item, ref_to_id) for item in config]
    if isinstance(config, dict):
        return {k: _resolve_variables_in_config(v, ref_to_id) for k, v in config.items()}
    return config


def _layout_positions(
    starter_ref: str,
    edges: list[GeneratedEdge],
    node_refs: list[str],
) -> dict[str, dict[str, float]]:
    positions: dict[str, dict[str, float]] = {}
    positions[starter_ref] = {"x": _STARTER_X, "y": _STARTER_Y}

    adjacency: dict[str, list[tuple[str, str]]] = {}
    for edge in edges:
        adjacency.setdefault(edge.source, []).append((edge.target, edge.source_handle))

    depth: dict[str, int] = {starter_ref: 0}
    queue = [starter_ref]
    while queue:
        current = queue.pop(0)
        for target, _handle in adjacency.get(current, []):
            if target not in depth:
                depth[target] = depth[current] + 1
                queue.append(target)

    max_depth = max(depth.values()) if depth else 0
    for ref in node_refs:
        if ref == starter_ref:
            continue
        d = depth.get(ref, max_depth + 1)
        positions[ref] = {"x": _STARTER_X + d * _H_SPACING, "y": _STARTER_Y}

    for edge in edges:
        if edge.source_handle == "true" and edge.target in positions:
            positions[edge.target]["y"] = _STARTER_Y - _V_BRANCH
        elif edge.source_handle == "false" and edge.target in positions:
            positions[edge.target]["y"] = _STARTER_Y + _V_BRANCH

    return positions


def _plan_to_react_flow(
    plan: GeneratedWorkflowPlan,
    catalog: dict,
    schema_key_map: dict[str, str],
) -> tuple[list, list]:
    ref_to_id: dict[str, str] = {}
    starter_types = {s["type"] for s in (catalog.get("starters") or [])}
    starter_ref: str | None = None

    for gen_node in plan.nodes:
        if gen_node.node_type in starter_types:
            starter_ref = gen_node.ref
        ref_to_id[gen_node.ref] = str(uuid.uuid4())

    positions = _layout_positions(
        starter_ref or plan.nodes[0].ref,
        plan.edges,
        [n.ref for n in plan.nodes],
    )

    react_nodes: list[dict] = []
    for gen_node in plan.nodes:
        node_def = lookup_node_def(catalog, gen_node.node_type)
        is_starter = gen_node.node_type in starter_types
        config = _apply_defaults(gen_node.node_type, gen_node.config, node_def)
        config = normalize_node_schemas(gen_node.node_type, config, schema_key_map)
        config = _resolve_variables_in_config(config, ref_to_id)
        pos = positions.get(gen_node.ref, {"x": _STARTER_X, "y": _STARTER_Y})

        react_nodes.append({
            "id":       ref_to_id[gen_node.ref],
            "type":     "fuse_node",
            "position": pos,
            "data": {
                "nodeType":  gen_node.node_type,
                "label":     gen_node.label or (node_def or {}).get("label", gen_node.node_type),
                "icon":      (node_def or {}).get("icon"),
                "config":    config,
                "isStarter": is_starter,
            },
        })

    react_edges: list[dict] = []
    for idx, gen_edge in enumerate(plan.edges):
        source_id = ref_to_id.get(gen_edge.source)
        target_id = ref_to_id.get(gen_edge.target)
        if not source_id or not target_id:
            continue
        handle = gen_edge.source_handle or "default"
        allowed = ("default", "true", "false", "item", "done")
        if handle not in allowed and not str(handle).startswith("case_"):
            handle = "default"
        react_edges.append({
            "id":           f"edge_{idx}_{uuid.uuid4().hex[:8]}",
            "source":       source_id,
            "target":       target_id,
            "sourceHandle": None if handle == "default" else handle,
        })

    return react_nodes, react_edges


def _build_user_prompt(prompt: str) -> str:
    extras = build_prompt_extras(prompt)
    base = f"## User goal\n\n{prompt.strip()}\n"
    if extras:
        base += f"\n{extras}\n"
    return base


# ─── Public API ───────────────────────────────────────────────────────────────

def generate_workflow_from_prompt(
    prompt: str,
    user_integrations: dict | None,
    *,
    workflow_id: str = "draft",
    owner_id: str = "",
    max_attempts: int = 2,
) -> dict[str, Any]:
    prompt = (prompt or "").strip()
    if not prompt:
        return {"success": False, "errors": ["Prompt is required."]}

    catalog = get_available_nodes(user_integrations)
    schema_key_map = build_schema_key_map(catalog)
    valid_types = {
        n["type"]
        for n in (catalog.get("starters") or []) + (catalog.get("actions") or [])
    }

    ai_provider = AIProvider()
    ai = ai_provider.get(CONFIG.MODELS.NONEY_CODE_GEN_20241001)
    base_model = ai.model
    structured = ai.with_structured_output(GeneratedWorkflowPlan, method="json_schema")

    user_message = _build_user_prompt(prompt)
    last_errors: list[str] = []

    # Phase 1: tool-based node discovery (once per request; retried with error context)
    discovery_messages = run_discovery_phase(base_model, user_message, catalog)

    for attempt in range(max_attempts):
        gen_messages = build_generation_messages(
            discovery_messages,
            extra=(
                "## Previous attempt failed validation\nFix these issues:\n"
                + "\n".join(f"- {e}" for e in last_errors)
                if last_errors else ""
            ),
        )

        try:
            plan: GeneratedWorkflowPlan = structured.invoke(gen_messages)
        except Exception as exc:
            return {"success": False, "errors": [f"AI generation failed: {exc}"]}

        if not plan or not plan.nodes:
            last_errors = ["AI returned an empty workflow."]
            continue

        unknown = {n.node_type for n in plan.nodes} - valid_types
        if unknown:
            last_errors = [
                f"Unknown node type(s): {', '.join(sorted(unknown))}. "
                "Use search_fuse_nodes and get_fuse_node_details first."
            ]
            continue

        fetched = get_fetched_node_types()
        unfetched = {n.node_type for n in plan.nodes} - fetched
        if unfetched and fetched:
            last_errors = [
                f"Node type(s) used without fetching details: {', '.join(sorted(unfetched))}. "
                "Call get_fuse_node_details for each type before generating."
            ]
            continue

        plan = GeneratedWorkflowPlan(
            name=plan.name,
            nodes=[
                GeneratedNode(**n)
                for n in apply_user_prompt_hints(
                    prompt,
                    [
                        GeneratedNode(**n)
                        for n in enrich_plan_node_configs(plan.nodes, schema_key_map)
                    ],
                )
            ],
            edges=plan.edges,
        )

        nodes, edges = _plan_to_react_flow(plan, catalog, schema_key_map)
        _, compile_errors = compile_workflow_graph(nodes, edges, workflow_id, owner_id)

        if compile_errors:
            last_errors = compile_errors
            continue

        name = (plan.name or "Untitled Workflow").strip()[:80] or "Untitled Workflow"
        return {
            "success": True,
            "name":    name,
            "nodes":   nodes,
            "edges":   edges,
            "errors":  [],
        }

    return {"success": False, "errors": last_errors or ["Failed to generate a valid workflow."]}
