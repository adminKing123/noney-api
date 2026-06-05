"""
fuse/runtime.py
===============
Singleton RuntimeManager that owns every active Fuse workflow execution.

Design
------
* One ``RuntimeManager`` instance per process (``runtime`` module-level object).
* Webhook workflows: no persistent daemon; each incoming HTTP request triggers
  a new ``ExecutionContext`` via ``run_workflow_async()``.  The manager just
  holds the compiled graph so the route handler can look it up.
* Schedule workflows: an APScheduler ``BackgroundScheduler`` manages cron /
  interval / date jobs.  The scheduler is started once and runs for the
  lifetime of the process.
* Thread safety: ``_active`` dict mutations are protected by ``_active_lock``.

Server-restart recovery
-----------------------
``restore_from_db(active_workflows)`` is called from ``app.py`` after the Flask
app is initialised.  It re-registers every workflow that was active at shutdown
so that schedules resume and webhook look-ups succeed.

One-shot schedules
------------------
When a schedule with ``repeat == "none"`` fires, the job automatically removes
itself from APScheduler (DateTrigger behaviour).  The ``_job_func`` callback
then calls ``_deactivate_after_one_shot()`` to mark the workflow as inactive in
Firestore so the frontend reflects the correct state.
"""

import logging
import threading
from datetime import datetime

logger = logging.getLogger(__name__)


# ─── Execution wrappers ────────────────────────────────────────────────────────

class WebhookExecution:
    """
    Represents an active webhook-triggered workflow.

    No daemon is needed — the compiled graph is held here so that the route
    handler can look it up by ``workflow_id`` and run the graph in a thread.
    """

    def __init__(self, workflow_id: str, compiled_graph: dict) -> None:
        self.workflow_id   = workflow_id
        self.compiled_graph = compiled_graph

    def start(self) -> None:
        logger.info("[FUSE] Webhook workflow '%s' is now active.", self.workflow_id)

    def stop(self) -> None:
        logger.info("[FUSE] Webhook workflow '%s' deactivated.", self.workflow_id)


class ScheduleExecution:
    """
    Represents an active scheduled workflow.

    Manages a single APScheduler job whose ID is ``fuse_schedule_<workflow_id>``.
    """

    def __init__(
        self,
        workflow_id: str,
        compiled_graph: dict,
        scheduler,
    ) -> None:
        self.workflow_id    = workflow_id
        self.compiled_graph = compiled_graph
        self._scheduler     = scheduler
        self._job_id        = f"fuse_schedule_{workflow_id}"

    # -- APScheduler callback --------------------------------------------------

    def _job_func(self) -> None:
        """Called by APScheduler when the scheduled time arrives."""
        from .executor import run_workflow  # lazy import

        trigger_data = {"fired_at": datetime.utcnow().isoformat() + "Z"}
        logger.info("[FUSE] Schedule fired for workflow '%s'.", self.workflow_id)

        try:
            run_workflow(self.compiled_graph, trigger_data)
        except Exception:
            logger.exception(
                "[FUSE] Schedule execution failed for workflow '%s'.", self.workflow_id
            )

        # DateTrigger jobs fire exactly once and are auto-removed by APScheduler.
        # Update Firestore status to inactive so the UI reflects this.
        repeat = self.compiled_graph["starter"]["config"].get("repeat", "none")
        if repeat == "none":
            _deactivate_after_one_shot(self.workflow_id)

    # -- Lifecycle -------------------------------------------------------------

    def start(self) -> None:
        from .nodes.schedule import build_aps_trigger, compute_end_date  # lazy

        config   = self.compiled_graph["starter"]["config"]
        trigger  = build_aps_trigger(config)
        end_date = compute_end_date(config.get("ends", "1y"))

        self._scheduler.add_job(
            func=self._job_func,
            trigger=trigger,
            id=self._job_id,
            end_date=end_date,
            replace_existing=True,
            misfire_grace_time=300,  # tolerate up to 5 min late firing (e.g. after restart)
        )
        logger.info("[FUSE] Schedule job registered for workflow '%s'.", self.workflow_id)

    def stop(self) -> None:
        try:
            self._scheduler.remove_job(self._job_id)
            logger.info("[FUSE] Schedule job removed for workflow '%s'.", self.workflow_id)
        except Exception:
            pass  # Job may have already been removed (e.g., one-shot that already fired)


# ─── Helpers ───────────────────────────────────────────────────────────────────

def _deactivate_after_one_shot(workflow_id: str) -> None:
    """
    Mark a one-shot workflow as inactive in Firestore after it fires.

    Runs in the APScheduler thread; errors are logged but never re-raised.
    """
    try:
        from db import db  # late import to avoid circular dep at module load

        now = datetime.utcnow().isoformat() + "Z"
        db.workflow._col().document(workflow_id).update({
            "status":     "inactive",
            "updated_at": now,
        })
        logger.info(
            "[FUSE] One-shot workflow '%s' set to inactive after firing.", workflow_id
        )
    except Exception:
        logger.exception(
            "[FUSE] Failed to deactivate one-shot workflow '%s' in Firestore.", workflow_id
        )


# ─── RuntimeManager ────────────────────────────────────────────────────────────

class RuntimeManager:
    """
    Process-wide singleton that manages all active Fuse workflow executions.

    Usage
    -----
    ::

        from fuse.runtime import runtime

        runtime.activate(workflow_id, compiled_graph)   # start
        runtime.deactivate(workflow_id)                 # stop
        execution = runtime.get_execution(workflow_id)  # look up
    """

    _instance: "RuntimeManager | None" = None
    _class_lock = threading.Lock()

    def __new__(cls) -> "RuntimeManager":
        with cls._class_lock:
            if cls._instance is None:
                inst = super().__new__(cls)
                inst._active: dict[str, WebhookExecution | ScheduleExecution] = {}
                inst._active_lock = threading.Lock()

                from apscheduler.schedulers.background import BackgroundScheduler
                inst._scheduler = BackgroundScheduler(daemon=True)
                inst._scheduler.start()

                cls._instance = inst
        return cls._instance

    # -- Public API ------------------------------------------------------------

    def activate(self, workflow_id: str, compiled_graph: dict) -> None:
        """
        Register and start a workflow execution.

        If an execution already exists for ``workflow_id`` it is stopped first,
        ensuring a clean handover when recompiling a running workflow.
        """
        self.deactivate(workflow_id)  # idempotent — no-op if not active

        starter_type = compiled_graph["starter"]["node_type"]

        if starter_type == "webhook":
            execution: WebhookExecution | ScheduleExecution = WebhookExecution(
                workflow_id, compiled_graph
            )
        elif starter_type == "schedule":
            execution = ScheduleExecution(workflow_id, compiled_graph, self._scheduler)
        else:
            raise ValueError(f"Unknown starter node type: '{starter_type}'")

        execution.start()

        with self._active_lock:
            self._active[workflow_id] = execution

    def deactivate(self, workflow_id: str) -> None:
        """Stop and remove the execution for ``workflow_id`` (no-op if not active)."""
        with self._active_lock:
            execution = self._active.pop(workflow_id, None)

        if execution is not None:
            execution.stop()

    def get_execution(self, workflow_id: str) -> WebhookExecution | ScheduleExecution | None:
        """Return the active execution for a workflow, or None if inactive."""
        with self._active_lock:
            return self._active.get(workflow_id)

    def is_active(self, workflow_id: str) -> bool:
        """Return True if the workflow currently has a registered execution."""
        with self._active_lock:
            return workflow_id in self._active

    def restore_from_db(self, active_workflows: list) -> None:
        """
        Re-register active workflow executions on server startup.

        Each item in ``active_workflows`` must be a Firestore workflow document
        dict with a ``compiled_graph`` field populated.
        """
        for wf in active_workflows:
            workflow_id    = wf.get("id", "")
            compiled_graph = wf.get("compiled_graph")

            if not compiled_graph:
                logger.warning(
                    "[FUSE] Active workflow '%s' has no compiled_graph — skipping restore.",
                    workflow_id,
                )
                continue

            try:
                self.activate(workflow_id, compiled_graph)
                logger.info("[FUSE] Restored active workflow '%s' from DB.", workflow_id)
            except Exception:
                logger.exception(
                    "[FUSE] Failed to restore workflow '%s' on startup.", workflow_id
                )

    def shutdown(self) -> None:
        """Gracefully stop all executions and the scheduler (call from atexit)."""
        with self._active_lock:
            for execution in self._active.values():
                execution.stop()
            self._active.clear()
        try:
            self._scheduler.shutdown(wait=False)
        except Exception:
            pass


# ─── Module-level singleton ────────────────────────────────────────────────────

runtime = RuntimeManager()
