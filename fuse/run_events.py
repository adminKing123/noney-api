"""
fuse/run_events.py
==================
Thread-safe pub/sub for live Fuse run updates over WebSocket.

Each ``run_id`` is a room; clients connected to ``/fuse/runs/<run_id>/live``
only receive events for that run. The executor calls ``emit_*`` from worker threads.
"""

from __future__ import annotations

import json
import logging
import threading
from typing import Any

logger = logging.getLogger(__name__)


class RunEventHub:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subscribers: dict[str, set[Any]] = {}
        self._active_node: dict[str, str | None] = {}

    def subscribe(self, run_id: str, websocket: Any) -> None:
        """Add a socket to the room for this run_id."""
        with self._lock:
            self._subscribers.setdefault(run_id, set()).add(websocket)

    def unsubscribe(self, run_id: str, websocket: Any) -> None:
        """Remove a socket from the run_id room."""
        with self._lock:
            subs = self._subscribers.get(run_id)
            if not subs:
                return
            subs.discard(websocket)
            if not subs:
                self._subscribers.pop(run_id, None)

    def get_active_node_id(self, run_id: str) -> str | None:
        with self._lock:
            return self._active_node.get(run_id)

    def _broadcast(self, run_id: str, payload: dict) -> None:
        with self._lock:
            sockets = list(self._subscribers.get(run_id, ()))
        if not sockets:
            return
        message = json.dumps(payload, default=str)
        dead: list[Any] = []
        for ws in sockets:
            try:
                ws.send(message)
            except Exception:
                dead.append(ws)
                logger.debug("[FUSE-WS] Dropping closed socket for run=%s", run_id)
        for ws in dead:
            self.unsubscribe(run_id, ws)

    def emit(self, run_id: str, event_type: str, **fields) -> None:
        self._broadcast(run_id, {"type": event_type, **fields})

    def emit_run_update(self, run_id: str, run: dict) -> None:
        self.emit(run_id, "run_update", run=run)

    def emit_node_started(
        self,
        run_id: str,
        *,
        node_id: str,
        node_type: str,
        node_label: str,
        started_at: str,
    ) -> None:
        with self._lock:
            self._active_node[run_id] = node_id
        self.emit(
            run_id,
            "node_started",
            node_id=node_id,
            node_type=node_type,
            node_label=node_label,
            started_at=started_at,
        )

    def emit_node_log(self, run_id: str, log: dict) -> None:
        with self._lock:
            if self._active_node.get(run_id) == log.get("node_id"):
                self._active_node[run_id] = None
        self.emit(run_id, "node_log", log=log)

    def emit_run_finished(self, run_id: str, run: dict) -> None:
        with self._lock:
            self._active_node.pop(run_id, None)
        self.emit(run_id, "run_finished", run=run)


hub = RunEventHub()


def emit_run_started(run_id: str, run: dict) -> None:
    hub.emit_run_update(run_id, run)


def emit_node_started(
    run_id: str,
    *,
    node_id: str,
    node_type: str,
    node_label: str,
    started_at: str,
) -> None:
    hub.emit_node_started(
        run_id,
        node_id=node_id,
        node_type=node_type,
        node_label=node_label,
        started_at=started_at,
    )


def emit_node_log(run_id: str, log: dict) -> None:
    hub.emit_node_log(run_id, log)


def emit_run_finished(run_id: str, run: dict) -> None:
    hub.emit_run_finished(run_id, run)
