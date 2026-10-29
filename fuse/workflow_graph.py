"""
Build in-memory execution graphs from slim Firestore workflow docs.

Canonical compile lives in ``fuse_versions``; ``fuse`` stores ``version_id``,
``fuse_runtime`` (integration webhooks only), and ``starter_type``.
"""

from __future__ import annotations

import copy
import logging
from typing import Any

logger = logging.getLogger(__name__)

RUNTIME_WEBHOOK_KEYS = ("webex_webhook", "github_webhook")


def extract_fuse_runtime(compiled_graph: dict) -> dict:
    """Persist only integration webhook metadata from an in-memory graph."""
    return {
        k: compiled_graph[k]
        for k in RUNTIME_WEBHOOK_KEYS
        if compiled_graph.get(k)
    }


def merge_version_runtime(
    version_graph: dict,
    version_id: str,
    fuse_runtime: dict | None,
    legacy_compiled: dict | None = None,
) -> dict:
    """Merge version compile plan with stored runtime webhook fields."""
    merged = copy.deepcopy(version_graph)
    merged["version_id"] = version_id

    runtime = dict(fuse_runtime or {})
    if legacy_compiled:
        for key in RUNTIME_WEBHOOK_KEYS:
            if key not in runtime and legacy_compiled.get(key):
                runtime[key] = legacy_compiled[key]

    for key, val in runtime.items():
        if val:
            merged[key] = val
    return merged


def load_execution_graph_for_workflow(workflow: dict) -> dict | None:
    """
    Load the full execution graph for an active workflow (cold start).

    At most one ``fuse_versions`` read when ``version_id`` is set.
    Falls back to legacy ``compiled_graph`` on the workflow doc.
    """
    from db import db  # noqa: PLC0415

    legacy = workflow.get("compiled_graph")
    version_id = workflow.get("version_id")
    fuse_runtime = workflow.get("fuse_runtime") or {}

    if version_id:
        version = db.workflow_version.get(version_id)
        version_graph = (version or {}).get("compiled_graph")
        if isinstance(version_graph, dict):
            return merge_version_runtime(
                version_graph,
                version_id,
                fuse_runtime,
                legacy if isinstance(legacy, dict) else None,
            )
        logger.warning(
            "[FUSE] Workflow '%s' version '%s' missing — trying legacy compiled_graph.",
            workflow.get("id"),
            version_id,
        )

    if isinstance(legacy, dict) and legacy.get("starter"):
        return legacy

    return None


def webhook_cleanup_graph(workflow: dict) -> dict:
    """Minimal graph shape for Webex/GitHub webhook teardown helpers."""
    legacy = workflow.get("compiled_graph") or {}
    fuse_runtime = workflow.get("fuse_runtime") or {}
    starter_type = workflow.get("starter_type") or (legacy.get("starter") or {}).get(
        "node_type", ""
    )
    graph: dict[str, Any] = {"starter": {"node_type": starter_type}}
    for key in RUNTIME_WEBHOOK_KEYS:
        if fuse_runtime.get(key):
            graph[key] = fuse_runtime[key]
        elif legacy.get(key):
            graph[key] = legacy[key]
    return graph


def is_runnable_graph(graph: dict | None) -> bool:
    return bool(
        graph
        and graph.get("version_id")
        and graph.get("starter")
        and graph.get("nodes") is not None
    )
