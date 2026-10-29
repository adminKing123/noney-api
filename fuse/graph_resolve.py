"""
Resolve the compiled graph to execute for a workflow trigger.

Hot path: use the in-memory graph from activate / lazy-load (no Firestore read).
Cold / incomplete: load ``fuse_versions`` once via ``workflow_graph``.
"""

from __future__ import annotations

import logging
from typing import Any

from fuse.workflow_graph import is_runnable_graph, load_execution_graph_for_workflow

logger = logging.getLogger(__name__)


def resolve_compiled_graph_for_run(execution: Any) -> dict:
    runtime_graph = execution.compiled_graph or {}

    if is_runnable_graph(runtime_graph):
        return runtime_graph

    from db import db  # noqa: PLC0415

    workflow = db.workflow.get_active_by_id(execution.workflow_id)
    if not workflow:
        logger.warning(
            "[FUSE] Active workflow '%s' not found — using in-memory graph.",
            execution.workflow_id,
        )
        return runtime_graph

    loaded = load_execution_graph_for_workflow(workflow)
    if loaded:
        execution.compiled_graph = loaded
        return loaded

    return runtime_graph
