"""
fuse/compiler.py
================
Compiles a React Flow graph (nodes + edges) into a deterministic, serialisable
execution plan (compiled_graph).

The compiled graph is stored in Firestore alongside the workflow document so that
the RuntimeManager can restore active workflows after a server restart without
needing to recompile.

Public API
----------
compile_workflow_graph(nodes, edges, workflow_id) -> (CompiledGraph | None, list[str])
compute_graph_hash(nodes, edges)                  -> str
"""

import hashlib
import json
from datetime import datetime
from typing import Any


# ─── Required config fields per node type ─────────────────────────────────────

_REQUIRED_FIELDS: dict[str, list[str]] = {
    "schedule":     ["date", "time"],
    # method is intentionally excluded — the route handler defaults to "POST"
    "webhook":      [],
    "get_notified": ["title", "body"],
    "if_else":      ["condition"],
}


# ─── Hash ─────────────────────────────────────────────────────────────────────

def compute_graph_hash(nodes: list, edges: list) -> str:
    """
    Compute a deterministic SHA-256 fingerprint of the workflow graph.

    Nodes and edges are sorted by ID before hashing so that the hash is
    independent of the order in which React Flow returns them.  Position data
    is intentionally included so a graph that is visually different (even if
    logically equivalent) produces the same hash — this is fine because we only
    use the hash to detect staleness, not semantic equivalence.
    """
    sorted_nodes = sorted(nodes, key=lambda n: n.get("id", ""))
    sorted_edges = sorted(edges, key=lambda e: e.get("id", ""))
    payload = json.dumps(
        {"nodes": sorted_nodes, "edges": sorted_edges},
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(payload.encode()).hexdigest()


# ─── Per-node validation ───────────────────────────────────────────────────────

def _validate_node_config(node_type: str, config: dict) -> list[str]:
    """
    Return a list of human-readable validation error strings for `config`.
    An empty list means the config is valid.
    """
    errors: list[str] = []
    config = config or {}

    # Check required fields
    for field in _REQUIRED_FIELDS.get(node_type, []):
        if not config.get(field):
            errors.append(f"Required field '{field}' is missing or empty.")

    # Condition builder sanity check
    if node_type == "if_else":
        cond = config.get("condition") or {}
        if not cond.get("variable"):
            errors.append("Condition must have a variable selected.")
        if not cond.get("operator"):
            errors.append("Condition must have an operator selected.")

    # Schedule: time must be parseable
    if node_type == "schedule":
        time_str = config.get("time", "")
        if time_str and not _is_valid_time(time_str):
            errors.append(f"Schedule time '{time_str}' is not a valid HH:MM value.")

    return errors


def _is_valid_time(time_str: str) -> bool:
    """Return True if `time_str` is HH:MM or a relative offset like '+5min'."""
    if time_str.startswith("+") and time_str.endswith("min"):
        try:
            int(time_str[1:-3])
            return True
        except ValueError:
            return False
    parts = time_str.split(":")
    if len(parts) != 2:
        return False
    try:
        h, m = int(parts[0]), int(parts[1])
        return 0 <= h <= 23 and 0 <= m <= 59
    except ValueError:
        return False


# ─── Main compiler ─────────────────────────────────────────────────────────────

def compile_workflow_graph(
    nodes: list,
    edges: list,
    workflow_id: str,
    owner_id: str = "",
) -> tuple[dict | None, list[str]]:
    """
    Compile a React Flow graph into an execution plan.

    Validation steps:
    1.  Exactly one starter node must be present.
    2.  All action nodes must be reachable from the starter.
    3.  Every node's config must pass the per-type validation rules.

    If any errors are found the function returns (None, errors).
    On success it returns (compiled_graph, []).

    Compiled graph shape
    --------------------
    {
        "workflow_id":  str,
        "compiled_at":  ISO-8601 str,
        "graph_hash":   str,
        "starter": {
            "node_id":   str,
            "node_type": str,   # "webhook" | "schedule"
            "config":    dict,
        },
        "adjacency": {
            # source_node_id -> handle -> [target_node_id, ...]
            "<node_id>": {
                "default": ["<node_id>"],   # regular nodes
                "true":    ["<node_id>"],   # if_else true branch
                "false":   ["<node_id>"],   # if_else false branch
            },
        },
        "nodes": {
            "<node_id>": {
                "node_type": str,
                "config":    dict,
                "label":     str,
            },
        },
    }
    """
    errors: list[str] = []

    # ── 1. Locate the starter node ────────────────────────────────────────────
    starter_nodes = [
        n for n in nodes if n.get("data", {}).get("isStarter")
    ]

    if not starter_nodes:
        errors.append(
            "No trigger node found. Add a Webhook or Schedule node to start the workflow."
        )
        return None, errors

    if len(starter_nodes) > 1:
        errors.append("Only one trigger node is allowed per workflow.")
        return None, errors

    starter = starter_nodes[0]
    starter_id   = starter["id"]
    starter_type = starter["data"].get("nodeType", "")
    starter_cfg  = starter["data"].get("config") or {}

    # ── 2. Validate starter config ────────────────────────────────────────────
    for err in _validate_node_config(starter_type, starter_cfg):
        label = starter["data"].get("label", "Trigger")
        errors.append(f"[{label}] {err}")

    # ── 3. Build adjacency map from edges ─────────────────────────────────────
    adjacency: dict[str, dict[str, list]] = {}
    for edge in edges:
        source = edge.get("source", "")
        target = edge.get("target", "")
        handle = edge.get("sourceHandle") or "default"
        if not source or not target:
            continue
        adjacency.setdefault(source, {}).setdefault(handle, []).append(target)

    # ── 4. BFS to find all reachable nodes ────────────────────────────────────
    reachable: set[str] = set()
    queue = [starter_id]
    while queue:
        current = queue.pop(0)
        for targets in adjacency.get(current, {}).values():
            for t in targets:
                if t not in reachable:
                    reachable.add(t)
                    queue.append(t)

    # ── 5. Validate each action node ─────────────────────────────────────────
    compiled_nodes: dict[str, dict] = {}
    for node in nodes:
        if node.get("data", {}).get("isStarter"):
            continue  # starter is handled above

        node_id   = node["id"]
        node_type = node["data"].get("nodeType", "")
        config    = node["data"].get("config") or {}
        label     = node["data"].get("label") or node_id

        if node_id not in reachable:
            errors.append(
                f"Node '{label}' is disconnected. Connect it to the workflow or remove it."
            )

        for err in _validate_node_config(node_type, config):
            errors.append(f"[{label}] {err}")

        compiled_nodes[node_id] = {
            "node_type": node_type,
            "config":    config,
            "label":     label,
        }

    # ── 6. Short-circuit if any errors ───────────────────────────────────────
    if errors:
        return None, errors

    # ── 7. Build the compiled graph ───────────────────────────────────────────
    compiled_graph: dict[str, Any] = {
        "workflow_id":  workflow_id,
        "owner_id":     owner_id,
        "compiled_at":  datetime.utcnow().isoformat() + "Z",
        "graph_hash":   compute_graph_hash(nodes, edges),
        "starter": {
            "node_id":   starter_id,
            "node_type": starter_type,
            "config":    starter_cfg,
        },
        "adjacency": adjacency,
        "nodes":     compiled_nodes,
    }

    return compiled_graph, []
