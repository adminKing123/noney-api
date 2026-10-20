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
5. For ``fork`` nodes with multiple outgoing edges, each branch runs in a
   thread pool (true parallel I/O).  A single outgoing edge stays on the
   main queue (no thread overhead).
6. For all other nodes, every outgoing edge's targets are enqueued.
7. Errors in individual nodes are caught, logged, and stored in the node's
   output — they do NOT abort the remaining workflow.

Persistence
-----------
Every execution creates a ``fuse_runs`` document (created at the start,
finalised at the end) and a ``fuse_run_logs`` document per node executed.
These records are NEVER deleted and will be used for pricing calculations.
"""

import copy
import logging
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


# ─── Time helpers ──────────────────────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _duration_ms(start_iso: str) -> int:
    """Return milliseconds elapsed since start_iso."""
    try:
        start = datetime.fromisoformat(start_iso.rstrip("Z")).replace(tzinfo=timezone.utc)
        return int((datetime.now(timezone.utc) - start).total_seconds() * 1000)
    except Exception:
        return 0


# ─── Execution context ─────────────────────────────────────────────────────────

class ExecutionContext:
    """
    Carries the mutable state for a single workflow execution run.

    Attributes
    ----------
    workflow_id  : ID of the workflow being executed.
    owner_id     : Firebase UID of the workflow owner.
    version_id   : ID of the fuse_versions doc used for this run (may be None).
    run_id       : Unique ID for this specific run (UUID4).  Also used as the
                   fuse_runs document ID so callers can look it up.
    triggered_at : ISO-8601 timestamp of when the run started.
    trigger_type : "webhook" | "schedule" | "manual"
    trigger_data : Raw data from the trigger event (webhook body, schedule time, etc.).
    node_outputs : Dict mapping node_id -> output dict produced by that node.
    """

    __slots__ = (
        "workflow_id", "owner_id", "version_id",
        "run_id", "triggered_at", "trigger_type",
        "trigger_data", "node_outputs", "_output_lock",
    )

    def __init__(
        self,
        workflow_id: str,
        owner_id: str,
        trigger_data: dict,
        trigger_type: str = "webhook",
        version_id: str | None = None,
    ) -> None:
        self.workflow_id  = workflow_id
        self.owner_id     = owner_id
        self.version_id   = version_id
        self.run_id       = str(uuid.uuid4())
        self.triggered_at = _now_iso()
        self.trigger_type = trigger_type
        self.trigger_data = trigger_data
        self.node_outputs: dict[str, dict] = {
            "system": {
                "workflow_id": self.workflow_id,
                "run_id": self.run_id,
                "triggered_at": self.triggered_at,
                "trigger_type": self.trigger_type,
            }
        }
        self._output_lock = threading.Lock()

    def set_output(self, node_id: str, output: dict) -> None:
        """Store a node's output for downstream variable resolution."""
        with self._output_lock:
            self.node_outputs[node_id] = output


# ─── Synchronous executor ──────────────────────────────────────────────────────

def run_workflow(
    compiled_graph: dict,
    trigger_data: dict,
    trigger_type: str = "webhook",
) -> ExecutionContext:
    """
    Execute a compiled workflow graph synchronously and return the final context.

    The function is deliberately stateless — all mutable state lives in the
    returned ``ExecutionContext``.  This makes it safe to call concurrently
    from multiple threads (e.g. simultaneous webhook hits).

    Every execution is persisted:
    - A ``fuse_runs`` document is created at the start (status="running") and
      updated at the end (status="success" | "failed").
    - A ``fuse_run_logs`` document is written for every node that executes.

    Args:
        compiled_graph: The output of ``fuse.compiler.compile_workflow_graph()``.
        trigger_data:   Starter-node output data injected before traversal begins.
        trigger_type:   "webhook" | "schedule" | "manual"

    Returns:
        The ``ExecutionContext`` after all reachable nodes have been executed.
    """
    from .nodes import HANDLERS  # noqa: PLC0415 — lazy to avoid circular imports
    from db import db             # noqa: PLC0415

    workflow_id = compiled_graph.get("workflow_id", "unknown")
    owner_id    = compiled_graph.get("owner_id", "")
    version_id  = compiled_graph.get("version_id")

    ctx = ExecutionContext(
        workflow_id  = workflow_id,
        owner_id     = owner_id,
        trigger_data = trigger_data,
        trigger_type = trigger_type,
        version_id   = version_id,
    )

    # ── Create the run record (status=running) ────────────────────────────────
    try:
        run_doc = db.workflow_run.create_run(
            run_id       = ctx.run_id,
            workflow_id  = workflow_id,
            owner_id     = owner_id,
            version_id   = version_id,
            trigger_type = trigger_type,
            trigger_data = trigger_data,
        )
        from fuse.run_events import emit_run_started  # noqa: PLC0415

        emit_run_started(ctx.run_id, run_doc)
    except Exception:
        logger.exception(
            "[FUSE] Failed to create run record — workflow=%s run=%s",
            workflow_id, ctx.run_id,
        )

    starter      = compiled_graph["starter"]
    starter_id   = starter["node_id"]
    starter_type = starter.get("node_type", "")
    starter_label = starter.get("label") or starter_type or "Trigger"
    adjacency    = compiled_graph.get("adjacency", {})
    nodes        = compiled_graph.get("nodes", {})

    # The starter's own output equals the trigger payload
    ctx.set_output(starter_id, trigger_data)

    logger.info(
        "[FUSE] Execution started — workflow=%s run=%s trigger_type=%s triggered_at=%s",
        workflow_id, ctx.run_id, trigger_type, ctx.triggered_at,
    )

    # Starter nodes are not part of the BFS queue — log them explicitly so runs
    # show the webhook / message / GitHub PR trigger as the first step.
    _write_starter_log(
        db           = db,
        ctx          = ctx,
        starter_id   = starter_id,
        starter_type = starter_type,
        starter_label = starter_label,
        trigger_data = trigger_data,
        starter_config = starter.get("config", {}),
    )
    nodes_succeeded = 1

    # BFS queue — seed with the immediate successors of the starter node
    queue: list[str] = []
    for targets in adjacency.get(starter_id, {}).values():
        queue.extend(targets)

    executed: set[str] = set()
    nodes_failed    = 0
    run_error: str | None = None

    # Calculate in-degree for join nodes based on compiled graph adjacency
    in_degrees: dict[str, int] = {}
    for src, handles in adjacency.items():
        for handle, targets in handles.items():
            for t in targets:
                in_degrees[t] = in_degrees.get(t, 0) + 1

    join_visits: dict[str, int] = {}

    while queue:
        node_id = queue.pop(0)

        node = nodes.get(node_id)
        if node and node.get("node_type") == "join":
            join_visits[node_id] = join_visits.get(node_id, 0) + 1
            if join_visits[node_id] < in_degrees.get(node_id, 1):
                # Wait for other branches
                continue

        if node_id in executed:
            continue
        executed.add(node_id)

        if node is None:
            logger.warning(
                "[FUSE] Node '%s' missing from compiled graph — skipping. "
                "(workflow=%s run=%s)",
                node_id, workflow_id, ctx.run_id,
            )
            continue

        node_type  = node.get("node_type", "")
        node_label = node.get("label", node_id)
        handler    = HANDLERS.get(node_type)

        if handler is None:
            logger.warning(
                "[FUSE] No handler for node type '%s' — skipping. (workflow=%s run=%s)",
                node_type, workflow_id, ctx.run_id,
            )
            _write_node_log(
                db          = db,
                ctx         = ctx,
                node_id     = node_id,
                node_type   = node_type,
                node_label  = node_label,
                status      = "skipped",
                started_at  = _now_iso(),
                finished_at = _now_iso(),
                duration_ms = 0,
                output      = None,
                error       = f"No handler registered for node type '{node_type}'",
                error_type  = "MissingHandlerError",
                config      = node.get("config", {}),
            )
            continue

        # ── Execute the node ──────────────────────────────────────────────────
        node_config  = node.get("config", {})
        node_started = _now_iso()
        output: dict
        node_status: str
        node_error: str | None     = None
        node_error_type: str | None = None

        from fuse.run_events import emit_node_started  # noqa: PLC0415

        log_input, log_config, log_variables = _node_execution_snapshot(
            ctx, node_config
        )
        emit_node_started(
            ctx.run_id,
            node_id=node_id,
            node_type=node_type,
            node_label=node_label,
            started_at=node_started,
            config=log_config,
            input=log_input,
            variables=log_variables,
        )

        try:
            logger.info(
                "[FUSE] ▶ Running node '%s' (type=%s) — workflow=%s run=%s",
                node_label, node_type, workflow_id, ctx.run_id,
            )
            output = handler.execute(node_config, ctx)
            logger.info(
                "[FUSE] ✔ Node '%s' finished — output = %s",
                node_label, output,
            )
            node_status = "success"
            nodes_succeeded += 1

        except Exception as exc:
            logger.exception(
                "[FUSE] Node '%s' (%s) raised an error. (workflow=%s run=%s)",
                node_label, node_type, workflow_id, ctx.run_id,
            )
            output        = {"error": str(exc), "success": False}
            node_status   = "error"
            node_error    = str(exc)
            node_error_type = type(exc).__name__
            nodes_failed  += 1

        node_finished  = _now_iso()
        node_duration  = _duration_ms(node_started)
        ctx.set_output(node_id, output)

        # Write node log (best-effort — never abort the run on logging failure)
        _write_node_log(
            db          = db,
            ctx         = ctx,
            node_id     = node_id,
            node_type   = node_type,
            node_label  = node_label,
            status      = node_status,
            started_at  = node_started,
            finished_at = node_finished,
            duration_ms = node_duration,
            output      = output,
            error       = node_error,
            error_type  = node_error_type,
            config      = node_config,
            input_snapshot = log_input,
            variables   = log_variables,
        )

        # ── Determine outgoing edges ──────────────────────────────────────────
        adj = adjacency.get(node_id, {})
        if node_type == "if_else":
            branch = "true" if output.get("result") else "false"
            for target in adj.get(branch, []):
                if target not in executed:
                    queue.append(target)
        elif node_type == "switch":
            branch = output.get("matched_handle") or "default"
            for target in adj.get(branch, []):
                if target not in executed:
                    queue.append(target)
        elif node_type == "for_each":
            items        = output.get("items", [])
            item_targets = list(adj.get("item", []))
            done_targets = list(adj.get("done", []))
            # Guard set: body BFS must not cross into the done branch or loop back
            done_set     = set(done_targets) | {node_id}

            for loop_idx, loop_item in enumerate(items):
                # Expose the current element to downstream body nodes
                ctx.node_outputs[node_id]["current_item"]  = loop_item
                ctx.node_outputs[node_id]["current_index"] = loop_idx

                logger.info(
                    "[FUSE] for_each — iteration %d/%d — workflow=%s run=%s",
                    loop_idx + 1, len(items), workflow_id, ctx.run_id,
                )

                ns, nf = _run_for_each_body(
                    item_targets   = item_targets,
                    adjacency      = adjacency,
                    nodes          = nodes,
                    ctx            = ctx,
                    done_set       = done_set,
                    HANDLERS       = HANDLERS,
                    db             = db,
                    workflow_id    = workflow_id,
                )
                nodes_succeeded += ns
                nodes_failed    += nf

            for target in done_targets:
                if target not in executed:
                    queue.append(target)
        elif node_type == "fork":
            fork_targets = [t for tgts in adj.values() for t in tgts]
            if len(fork_targets) > 1:
                parallel_state = _ParallelRunState(executed, join_visits, in_degrees)
                ns, nf = _run_parallel_fork_branches(
                    branch_starts=fork_targets,
                    adjacency=adjacency,
                    nodes=nodes,
                    ctx=ctx,
                    state=parallel_state,
                    handlers=HANDLERS,
                    db=db,
                    workflow_id=workflow_id,
                )
                nodes_succeeded += ns
                nodes_failed += nf
            else:
                for target in fork_targets:
                    if target not in executed:
                        queue.append(target)
        else:
            for targets in adj.values():
                for target in targets:
                    if target not in executed:
                        queue.append(target)

    # ── Finalise the run record ───────────────────────────────────────────────
    run_status = "failed" if nodes_failed > 0 else "success"
    node_count = len(executed) + 1  # include the starter trigger node

    logger.info(
        "[FUSE] Execution finished — workflow=%s run=%s status=%s "
        "nodes=%d succeeded=%d failed=%d",
        workflow_id, ctx.run_id, run_status,
        node_count, nodes_succeeded, nodes_failed,
    )

    try:
        db.workflow_run.finish_run(
            run_id          = ctx.run_id,
            status          = run_status,
            node_count      = node_count,
            nodes_succeeded = nodes_succeeded,
            nodes_failed    = nodes_failed,
            started_at      = ctx.triggered_at,
            error           = run_error,
        )
        from fuse.run_events import emit_run_finished  # noqa: PLC0415

        finished_run = db.workflow_run.get_run(ctx.run_id, ctx.owner_id)
        if finished_run:
            emit_run_finished(ctx.run_id, finished_run)
    except Exception:
        logger.exception(
            "[FUSE] Failed to finalise run record — workflow=%s run=%s",
            workflow_id, ctx.run_id,
        )

    return ctx


# ─── Internal helpers ──────────────────────────────────────────────────────────

_MAX_FORK_PARALLEL_WORKERS = 32


class _ParallelRunState:
    """Thread-safe view of ``executed`` + ``join_visits`` during fork branches."""

    __slots__ = ("lock", "executed", "join_visits", "in_degrees")

    def __init__(
        self,
        executed: set[str],
        join_visits: dict[str, int],
        in_degrees: dict[str, int],
    ) -> None:
        self.lock = threading.Lock()
        self.executed = executed
        self.join_visits = join_visits
        self.in_degrees = in_degrees

    def claim(self, node_id: str, nodes: dict) -> tuple[bool, dict | None]:
        """
        Decide whether ``node_id`` should run in this worker.

        Returns ``(False, None)`` when the node is already done or a join is
        still waiting for sibling branches.
        """
        with self.lock:
            node = nodes.get(node_id)
            if node and node.get("node_type") == "join":
                self.join_visits[node_id] = self.join_visits.get(node_id, 0) + 1
                if self.join_visits[node_id] < self.in_degrees.get(node_id, 1):
                    return False, None
            if node_id in self.executed:
                return False, None
            self.executed.add(node_id)
            return True, node


def _fork_outgoing_targets(adjacency: dict, node_id: str) -> list[str]:
    adj = adjacency.get(node_id, {})
    return [t for tgts in adj.values() for t in tgts]


def _run_parallel_fork_branches(
    branch_starts: list[str],
    adjacency: dict,
    nodes: dict,
    ctx: ExecutionContext,
    state: _ParallelRunState,
    handlers: dict,
    db,
    workflow_id: str,
) -> tuple[int, int]:
    """Run each fork branch in a worker thread; return (succeeded, failed) counts."""
    if not branch_starts:
        return 0, 0

    logger.info(
        "[FUSE] fork — running %d branches in parallel — workflow=%s run=%s",
        len(branch_starts),
        workflow_id,
        ctx.run_id,
    )

    workers = min(len(branch_starts), _MAX_FORK_PARALLEL_WORKERS)
    nodes_succeeded = 0
    nodes_failed = 0

    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [
            pool.submit(
                _run_fork_branch_worker,
                start_id,
                adjacency,
                nodes,
                ctx,
                state,
                handlers,
                db,
                workflow_id,
            )
            for start_id in branch_starts
        ]
        for future in as_completed(futures):
            ns, nf = future.result()
            nodes_succeeded += ns
            nodes_failed += nf

    return nodes_succeeded, nodes_failed


def _run_fork_branch_worker(
    start_id: str,
    adjacency: dict,
    nodes: dict,
    ctx: ExecutionContext,
    state: _ParallelRunState,
    handlers: dict,
    db,
    workflow_id: str,
) -> tuple[int, int]:
    """BFS from one fork outlet until the branch queue is drained."""
    branch_queue: list[str] = [start_id]
    nodes_succeeded = 0
    nodes_failed = 0

    while branch_queue:
        node_id = branch_queue.pop(0)
        should_run, node = state.claim(node_id, nodes)
        if not should_run:
            continue

        if node is None:
            logger.warning(
                "[FUSE] fork branch — node '%s' missing from compiled graph "
                "(workflow=%s run=%s)",
                node_id,
                workflow_id,
                ctx.run_id,
            )
            continue

        node_type = node.get("node_type", "")
        node_label = node.get("label", node_id)
        handler = handlers.get(node_type)
        node_config = node.get("config", {})
        node_started = _now_iso()

        if handler is None:
            logger.warning(
                "[FUSE] fork branch — no handler for node type '%s' "
                "(workflow=%s run=%s)",
                node_type,
                workflow_id,
                ctx.run_id,
            )
            _write_node_log(
                db=db,
                ctx=ctx,
                node_id=node_id,
                node_type=node_type,
                node_label=node_label,
                status="skipped",
                started_at=node_started,
                finished_at=_now_iso(),
                duration_ms=0,
                output=None,
                error=f"No handler registered for node type '{node_type}'",
                error_type="MissingHandlerError",
                config=node_config,
            )
            continue

        from fuse.run_events import emit_node_started  # noqa: PLC0415

        log_input, log_config, log_variables = _node_execution_snapshot(ctx, node_config)
        emit_node_started(
            ctx.run_id,
            node_id=node_id,
            node_type=node_type,
            node_label=node_label,
            started_at=node_started,
            config=log_config,
            input=log_input,
            variables=log_variables,
        )

        node_error: str | None = None
        node_error_type: str | None = None
        try:
            logger.info(
                "[FUSE] fork branch ▶ '%s' (type=%s) — workflow=%s run=%s",
                node_label,
                node_type,
                workflow_id,
                ctx.run_id,
            )
            output = handler.execute(node_config, ctx)
            node_status = "success"
            nodes_succeeded += 1
        except Exception as exc:
            logger.exception(
                "[FUSE] fork branch — node '%s' (%s) raised an error "
                "(workflow=%s run=%s)",
                node_label,
                node_type,
                workflow_id,
                ctx.run_id,
            )
            output = {"error": str(exc), "success": False}
            node_status = "error"
            node_error = str(exc)
            node_error_type = type(exc).__name__
            nodes_failed += 1

        node_finished = _now_iso()
        ctx.set_output(node_id, output)
        _write_node_log(
            db=db,
            ctx=ctx,
            node_id=node_id,
            node_type=node_type,
            node_label=node_label,
            status=node_status,
            started_at=node_started,
            finished_at=node_finished,
            duration_ms=_duration_ms(node_started),
            output=output,
            error=node_error,
            error_type=node_error_type,
            config=node_config,
            input_snapshot=log_input,
            variables=log_variables,
        )

        adj = adjacency.get(node_id, {})
        if node_type == "if_else":
            branch = "true" if output.get("result") else "false"
            for target in adj.get(branch, []):
                branch_queue.append(target)
        elif node_type == "switch":
            branch = output.get("matched_handle") or "default"
            for target in adj.get(branch, []):
                branch_queue.append(target)
        elif node_type == "for_each":
            items = output.get("items", [])
            item_targets = list(adj.get("item", []))
            done_targets = list(adj.get("done", []))
            done_set = set(done_targets) | {node_id}
            for loop_idx, loop_item in enumerate(items):
                ctx.node_outputs[node_id]["current_item"] = loop_item
                ctx.node_outputs[node_id]["current_index"] = loop_idx
                ns, nf = _run_for_each_body(
                    item_targets=item_targets,
                    adjacency=adjacency,
                    nodes=nodes,
                    ctx=ctx,
                    done_set=done_set,
                    HANDLERS=handlers,
                    db=db,
                    workflow_id=workflow_id,
                )
                nodes_succeeded += ns
                nodes_failed += nf
            for target in done_targets:
                branch_queue.append(target)
        elif node_type == "fork":
            nested = _fork_outgoing_targets(adjacency, node_id)
            if len(nested) > 1:
                ns, nf = _run_parallel_fork_branches(
                    branch_starts=nested,
                    adjacency=adjacency,
                    nodes=nodes,
                    ctx=ctx,
                    state=state,
                    handlers=handlers,
                    db=db,
                    workflow_id=workflow_id,
                )
                nodes_succeeded += ns
                nodes_failed += nf
            else:
                branch_queue.extend(nested)
        else:
            for targets in adj.values():
                branch_queue.extend(targets)

    return nodes_succeeded, nodes_failed


def _run_for_each_body(
    item_targets: list[str],
    adjacency: dict,
    nodes: dict,
    ctx,
    done_set: set[str],
    HANDLERS: dict,
    db,
    workflow_id: str,
) -> tuple[int, int]:
    """
    Execute the body sub-graph of a ``for_each`` node once (one iteration).

    The body is a BFS starting from ``item_targets``.  Traversal stops before
    any node in ``done_set`` (the for_each node itself + its done-handle targets)
    so the loop body cannot spill into downstream (post-loop) nodes.

    Each call gets its own ``body_executed`` set, so the same body nodes run
    again on the next iteration.  The caller must update
    ``ctx.node_outputs[for_each_node_id]["current_item"]`` and
    ``ctx.node_outputs[for_each_node_id]["current_index"]`` before calling.

    Returns ``(nodes_succeeded, nodes_failed)`` for the iteration.
    """
    body_queue: list[str] = list(item_targets)
    body_executed: set[str] = set()
    body_join_visits: dict[str, int] = {}
    nodes_succeeded = 0
    nodes_failed    = 0

    while body_queue:
        body_nid = body_queue.pop(0)

        # Boundary: do not enter the done branch or loop back to for_each
        if body_nid in done_set:
            continue

        body_node = nodes.get(body_nid)

        # Join synchronisation within the body
        if body_node and body_node.get("node_type") == "join":
            body_join_visits[body_nid] = body_join_visits.get(body_nid, 0) + 1
            in_deg = sum(
                1
                for src, handles in adjacency.items()
                for tgts in handles.values()
                if body_nid in tgts and src not in done_set
            )
            if body_join_visits[body_nid] < max(in_deg, 1):
                continue

        if body_nid in body_executed:
            continue
        body_executed.add(body_nid)

        if body_node is None:
            logger.warning(
                "[FUSE] for_each body — node '%s' missing from compiled graph "
                "(workflow=%s run=%s)",
                body_nid, workflow_id, ctx.run_id,
            )
            continue

        body_node_type  = body_node.get("node_type", "")
        body_node_label = body_node.get("label", body_nid)
        body_handler    = HANDLERS.get(body_node_type)
        body_started    = _now_iso()

        if body_handler is None:
            logger.warning(
                "[FUSE] for_each body — no handler for node type '%s' "
                "(workflow=%s run=%s)",
                body_node_type, workflow_id, ctx.run_id,
            )
            _write_node_log(
                db          = db,
                ctx         = ctx,
                node_id     = body_nid,
                node_type   = body_node_type,
                node_label  = body_node_label,
                status      = "skipped",
                started_at  = body_started,
                finished_at = _now_iso(),
                duration_ms = 0,
                output      = None,
                error       = f"No handler registered for node type '{body_node_type}'",
                error_type  = "MissingHandlerError",
                config      = body_node.get("config", {}),
            )
            continue

        body_config = body_node.get("config", {})
        body_output: dict
        body_status: str
        body_error: str | None      = None
        body_error_type: str | None = None

        from fuse.run_events import emit_node_started  # noqa: PLC0415

        body_log_input, body_log_config, body_log_variables = _node_execution_snapshot(
            ctx, body_config
        )
        emit_node_started(
            ctx.run_id,
            node_id=body_nid,
            node_type=body_node_type,
            node_label=body_node_label,
            started_at=body_started,
            config=body_log_config,
            input=body_log_input,
            variables=body_log_variables,
        )

        try:
            logger.info(
                "[FUSE] for_each body ▶ '%s' (type=%s) — workflow=%s run=%s",
                body_node_label, body_node_type, workflow_id, ctx.run_id,
            )
            body_output = body_handler.execute(body_config, ctx)
            body_status = "success"
            nodes_succeeded += 1
        except Exception as exc:
            logger.exception(
                "[FUSE] for_each body — node '%s' (%s) raised an error "
                "(workflow=%s run=%s)",
                body_node_label, body_node_type, workflow_id, ctx.run_id,
            )
            body_output      = {"error": str(exc), "success": False}
            body_status      = "error"
            body_error       = str(exc)
            body_error_type  = type(exc).__name__
            nodes_failed    += 1

        body_finished = _now_iso()
        ctx.set_output(body_nid, body_output)

        _write_node_log(
            db          = db,
            ctx         = ctx,
            node_id     = body_nid,
            node_type   = body_node_type,
            node_label  = body_node_label,
            status      = body_status,
            started_at  = body_started,
            finished_at = body_finished,
            duration_ms = _duration_ms(body_started),
            output      = body_output,
            error       = body_error,
            error_type  = body_error_type,
            config      = body_config,
            input_snapshot = body_log_input,
            variables   = body_log_variables,
        )

        # Enqueue next body nodes (respecting if_else branching within the body)
        body_adj = adjacency.get(body_nid, {})
        if body_node_type == "if_else":
            branch = "true" if body_output.get("result") else "false"
            for t in body_adj.get(branch, []):
                if t not in body_executed and t not in done_set:
                    body_queue.append(t)
        elif body_node_type == "switch":
            branch = body_output.get("matched_handle") or "default"
            for t in body_adj.get(branch, []):
                if t not in body_executed and t not in done_set:
                    body_queue.append(t)
        else:
            for tgts in body_adj.values():
                for t in tgts:
                    if t not in body_executed and t not in done_set:
                        body_queue.append(t)

    return nodes_succeeded, nodes_failed


def _write_starter_log(
    db,
    ctx: ExecutionContext,
    starter_id: str,
    starter_type: str,
    starter_label: str,
    trigger_data: dict,
    starter_config: dict | None = None,
) -> None:
    """Persist a fuse_run_logs entry for the trigger/starter node."""
    started_at = ctx.triggered_at
    finished_at = _now_iso()

    logger.info(
        "[FUSE] ▶ Starter '%s' (type=%s) — workflow=%s run=%s",
        starter_label, starter_type, ctx.workflow_id, ctx.run_id,
    )

    if starter_type == "webhook":
        logger.info(
            "[FUSE]   method=%s body=%s query_params=%s",
            trigger_data.get("method", "?"),
            trigger_data.get("body"),
            trigger_data.get("query_params"),
        )
    elif starter_type == "webex_message":
        logger.info(
            "[FUSE]   message_id=%s room_id=%s person_email=%s",
            trigger_data.get("message_id"),
            trigger_data.get("room_id"),
            trigger_data.get("person_email"),
        )
    elif starter_type == "github_pull_request":
        logger.info(
            "[FUSE]   pr_id=%s action=%s repo=%s",
            trigger_data.get("pr_id"),
            trigger_data.get("action"),
            trigger_data.get("repo_name"),
        )

    cfg = starter_config or {}
    _, log_config, log_variables = _node_execution_snapshot(ctx, cfg)
    _write_node_log(
        db          = db,
        ctx         = ctx,
        node_id     = starter_id,
        node_type   = starter_type,
        node_label  = starter_label,
        status      = "success",
        started_at  = started_at,
        finished_at = finished_at,
        duration_ms = _duration_ms(started_at),
        output      = trigger_data,
        error       = None,
        error_type  = None,
        config      = log_config,
        input_snapshot = {},
        variables   = log_variables,
    )


def _node_execution_snapshot(ctx: ExecutionContext, config: dict) -> tuple[dict, dict, dict]:
    """Upstream outputs, config copy, and resolved {{variables}} at execute time."""
    from fuse.variable_resolver import resolve_variables_map  # noqa: PLC0415

    cfg = copy.deepcopy(config or {})
    inp = copy.deepcopy(ctx.node_outputs)
    variables = resolve_variables_map(cfg, ctx.node_outputs)
    return inp, cfg, variables


def _should_persist_log_field(config: dict | None, field: str) -> bool:
    """Run-log save toggles on node config (default on when unset)."""
    if not config:
        return True
    return config.get(field, True) is not False


def _output_for_log(config: dict | None, output: dict | None) -> dict | None:
    if output is None or not _should_persist_log_field(config, "save_output"):
        return None
    return output


def _write_node_log(
    db,
    ctx: ExecutionContext,
    node_id: str,
    node_type: str,
    node_label: str,
    status: str,
    started_at: str,
    finished_at: str,
    duration_ms: int,
    output: dict | None,
    error: str | None,
    error_type: str | None,
    config: dict | None = None,
    input_snapshot: dict | None = None,
    variables: dict | None = None,
) -> None:
    """Write a fuse_run_logs document.  Silently swallows exceptions."""
    try:
        if config is not None:
            snap_input, snap_config, snap_vars = _node_execution_snapshot(ctx, config)
            config = snap_config
            if input_snapshot is None:
                input_snapshot = snap_input
            if variables is None:
                variables = snap_vars

        log_output = _output_for_log(config, output)
        log_input = (
            input_snapshot
            if _should_persist_log_field(config, "save_input")
            else None
        )
        log_config = (
            config if _should_persist_log_field(config, "save_config") else None
        )
        log_variables = (
            variables
            if _should_persist_log_field(config, "save_variables")
            else None
        )

        log_id, stored_log = db.workflow_run.write_node_log(
            run_id      = ctx.run_id,
            workflow_id = ctx.workflow_id,
            owner_id    = ctx.owner_id,
            node_id     = node_id,
            node_type   = node_type,
            node_label  = node_label,
            status      = status,
            started_at  = started_at,
            finished_at = finished_at,
            duration_ms = duration_ms,
            output      = log_output,
            input       = log_input,
            config      = log_config,
            variables   = log_variables,
            error       = error,
            error_type  = error_type,
        )
        from fuse.run_events import emit_node_log  # noqa: PLC0415

        emit_node_log(ctx.run_id, stored_log)
    except Exception:
        logger.exception(
            "[FUSE] Failed to write node log — run=%s node=%s",
            ctx.run_id, node_id,
        )


# ─── Async wrapper ─────────────────────────────────────────────────────────────

def run_workflow_async(
    compiled_graph: dict,
    trigger_data: dict,
    trigger_type: str = "webhook",
) -> None:
    """
    Fire-and-forget: execute a workflow in a daemon background thread.

    Exceptions inside ``run_workflow()`` are caught and logged by that function.
    This wrapper exists solely to avoid blocking the HTTP request handler.
    """
    thread = threading.Thread(
        target=run_workflow,
        args=(compiled_graph, trigger_data, trigger_type),
        daemon=True,
        name=f"fuse-exec-{compiled_graph.get('workflow_id', 'unknown')}",
    )
    thread.start()
