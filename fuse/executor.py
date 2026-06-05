"""
fuse/executor.py
================
Workflow DAG executor.

``run_workflow()``       — synchronous, returns the final ExecutionContext.
``run_workflow_async()`` — fire-and-forget daemon thread wrapper.

Execution model
---------------
1. The starter node's output is pre-populated with ``trigger_data`` (webhook
   request body / schedule fire time).
2. The executor performs a BFS traversal from the starter's outgoing edges.
3. Each visited node is executed exactly once (``executed`` set guards this).
4. For ``if_else`` nodes, only the branch matching ``output["result"]``
   (``"true"`` or ``"false"``) is enqueued.
5. For all other nodes, every outgoing edge's targets are enqueued.
6. Errors in individual nodes are caught, logged, and stored in the node's
   output — they do NOT abort the remaining workflow.
"""

import logging
import threading
import uuid
from datetime import datetime

logger = logging.getLogger(__name__)


# ─── Execution context ─────────────────────────────────────────────────────────

class ExecutionContext:
    """
    Carries the mutable state for a single workflow execution run.

    Attributes
    ----------
    workflow_id  : ID of the workflow being executed.
    run_id       : Unique ID for this specific run (UUID4).
    triggered_at : ISO-8601 timestamp of when the run started.
    trigger_data : Raw data from the trigger event (webhook body, schedule time, etc.).
    node_outputs : Dict mapping node_id -> output dict produced by that node.
    """

    __slots__ = ("workflow_id", "run_id", "triggered_at", "trigger_data", "node_outputs")

    def __init__(self, workflow_id: str, trigger_data: dict) -> None:
        self.workflow_id  = workflow_id
        self.run_id       = str(uuid.uuid4())
        self.triggered_at = datetime.utcnow().isoformat() + "Z"
        self.trigger_data = trigger_data
        self.node_outputs: dict[str, dict] = {}

    def set_output(self, node_id: str, output: dict) -> None:
        """Store a node's output for downstream variable resolution."""
        self.node_outputs[node_id] = output


# ─── Synchronous executor ──────────────────────────────────────────────────────

def run_workflow(compiled_graph: dict, trigger_data: dict) -> ExecutionContext:
    """
    Execute a compiled workflow graph synchronously and return the final context.

    The function is deliberately stateless — all mutable state lives in the
    returned ``ExecutionContext``.  This makes it safe to call concurrently
    from multiple threads (e.g. simultaneous webhook hits).

    Args:
        compiled_graph: The output of ``fuse.compiler.compile_workflow_graph()``.
        trigger_data:   Starter-node output data injected before traversal begins.

    Returns:
        The ``ExecutionContext`` after all reachable nodes have been executed.
    """
    # Lazy import to avoid circular-dependency issues at module load time
    from .nodes import HANDLERS  # noqa: PLC0415

    workflow_id = compiled_graph.get("workflow_id", "unknown")
    ctx         = ExecutionContext(workflow_id, trigger_data)

    starter_id = compiled_graph["starter"]["node_id"]
    adjacency  = compiled_graph.get("adjacency", {})
    nodes      = compiled_graph.get("nodes", {})

    # The starter's own output equals the trigger payload
    ctx.set_output(starter_id, trigger_data)

    logger.info(
        "[FUSE] Execution started — workflow=%s run=%s triggered_at=%s",
        workflow_id, ctx.run_id, ctx.triggered_at,
    )
    logger.info(
        "[FUSE] trigger_data = %s",
        trigger_data,
    )

    # BFS queue — seed with the immediate successors of the starter node
    queue: list[str] = []
    for targets in adjacency.get(starter_id, {}).values():
        queue.extend(targets)

    executed: set[str] = set()

    while queue:
        node_id = queue.pop(0)

        if node_id in executed:
            continue
        executed.add(node_id)

        node = nodes.get(node_id)
        if node is None:
            logger.warning(
                "[FUSE] Node '%s' missing from compiled graph — skipping. (workflow=%s run=%s)",
                node_id, workflow_id, ctx.run_id,
            )
            continue

        node_type = node.get("node_type", "")
        handler   = HANDLERS.get(node_type)
        if handler is None:
            logger.warning(
                "[FUSE] No handler for node type '%s' — skipping. (workflow=%s run=%s)",
                node_type, workflow_id, ctx.run_id,
            )
            continue

        # Execute the node; catch and record errors without aborting the run
        try:
            logger.info(
                "[FUSE] ▶ Running node '%s' (type=%s) — workflow=%s run=%s",
                node.get("label", node_id), node_type, workflow_id, ctx.run_id,
            )
            logger.debug(
                "[FUSE]   config  = %s",
                node.get("config", {}),
            )
            output = handler.execute(node.get("config", {}), ctx)
            logger.info(
                "[FUSE] ✔ Node '%s' finished — output = %s",
                node.get("label", node_id), output,
            )
        except Exception:
            label = node.get("label", node_id)
            logger.exception(
                "[FUSE] Node '%s' (%s) raised an error. (workflow=%s run=%s)",
                label, node_type, workflow_id, ctx.run_id,
            )
            output = {"error": "Node execution failed", "success": False}

        ctx.set_output(node_id, output)

        # Determine which outgoing edges to follow
        adj = adjacency.get(node_id, {})
        if node_type == "if_else":
            branch = "true" if output.get("result") else "false"
            for target in adj.get(branch, []):
                if target not in executed:
                    queue.append(target)
        else:
            for targets in adj.values():
                for target in targets:
                    if target not in executed:
                        queue.append(target)

    logger.info(
        "[FUSE] Execution finished — workflow=%s run=%s nodes_executed=%d",
        workflow_id, ctx.run_id, len(executed),
    )
    return ctx


# ─── Async wrapper ─────────────────────────────────────────────────────────────

def run_workflow_async(compiled_graph: dict, trigger_data: dict) -> None:
    """
    Fire-and-forget: execute a workflow in a daemon background thread.

    Exceptions inside ``run_workflow()`` are caught and logged by that function.
    This wrapper exists solely to avoid blocking the HTTP request handler.
    """
    thread = threading.Thread(
        target=run_workflow,
        args=(compiled_graph, trigger_data),
        daemon=True,
        name=f"fuse-exec-{compiled_graph.get('workflow_id', 'unknown')}",
    )
    thread.start()
