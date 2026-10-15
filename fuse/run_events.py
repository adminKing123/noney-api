"""
fuse/run_events.py
==================
Thread-safe pub/sub for live Fuse run updates over WebSocket.

Rooms:
  run:{run_id}         — run detail page (/fuse/runs/<run_id>/live)
  workflow:{workflow_id} — run history list (/fuse/workflows/<id>/runs/live)
"""

from __future__ import annotations

import json
import logging
import threading
from typing import Any

logger = logging.getLogger(__name__)


def _run_room(run_id: str) -> str:
    return f"run:{run_id}"


def _workflow_room(workflow_id: str) -> str:
    return f"workflow:{workflow_id}"


class RunEventHub:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subscribers: dict[str, set[Any]] = {}
        self._active_node: dict[str, str | None] = {}

    def subscribe(self, room: str, websocket: Any) -> None:
        with self._lock:
            self._subscribers.setdefault(room, set()).add(websocket)

    def unsubscribe(self, room: str, websocket: Any) -> None:
        with self._lock:
            subs = self._subscribers.get(room)
            if not subs:
                return
            subs.discard(websocket)
            if not subs:
                self._subscribers.pop(room, None)

    def subscribe_run(self, run_id: str, websocket: Any) -> None:
        self.subscribe(_run_room(run_id), websocket)

    def unsubscribe_run(self, run_id: str, websocket: Any) -> None:
        self.unsubscribe(_run_room(run_id), websocket)

    def subscribe_workflow(self, workflow_id: str, websocket: Any) -> None:
        self.subscribe(_workflow_room(workflow_id), websocket)

    def unsubscribe_workflow(self, workflow_id: str, websocket: Any) -> None:
        self.unsubscribe(_workflow_room(workflow_id), websocket)

    def get_active_node_id(self, run_id: str) -> str | None:
        with self._lock:
            return self._active_node.get(run_id)

    def _broadcast(self, room: str, payload: dict) -> None:
        with self._lock:
            sockets = list(self._subscribers.get(room, ()))
        if not sockets:
            return
        message = json.dumps(payload, default=str)
        dead: list[Any] = []
        for ws in sockets:
            try:
                ws.send(message)
            except Exception:
                dead.append(ws)
                logger.debug("[FUSE-WS] Dropping closed socket for room=%s", room)
        for ws in dead:
            self.unsubscribe(room, ws)

    def emit_to_run(self, run_id: str, event_type: str, **fields) -> None:
        self._broadcast(_run_room(run_id), {"type": event_type, **fields})

    def emit_to_workflow(self, workflow_id: str | None, event_type: str, **fields) -> None:
        if not workflow_id:
            return
        self._broadcast(_workflow_room(workflow_id), {"type": event_type, **fields})

    def emit_run_update(self, run_id: str, run: dict) -> None:
        self.emit_to_run(run_id, "run_update", run=run)

    def emit_node_started(
        self,
        run_id: str,
        *,
        node_id: str,
        node_type: str,
        node_label: str,
        started_at: str,
        config: dict | None = None,
        input: dict | None = None,
        variables: dict | None = None,
    ) -> None:
        with self._lock:
            self._active_node[run_id] = node_id
        payload: dict = {
            "node_id": node_id,
            "node_type": node_type,
            "node_label": node_label,
            "started_at": started_at,
        }
        if config is not None:
            payload["config"] = config
        if input is not None:
            payload["input"] = input
        if variables is not None:
            payload["variables"] = variables
        self.emit_to_run(run_id, "node_started", **payload)

    def emit_node_log(self, run_id: str, log: dict) -> None:
        with self._lock:
            if self._active_node.get(run_id) == log.get("node_id"):
                self._active_node[run_id] = None
        self.emit_to_run(run_id, "node_log", log=log)

    def emit_run_finished(self, run_id: str, run: dict) -> None:
        with self._lock:
            self._active_node.pop(run_id, None)
        self.emit_to_run(run_id, "run_finished", run=run)


hub = RunEventHub()


def _workflow_id_from_run(run: dict) -> str | None:
    return run.get("workflow_id")


def emit_run_started(run_id: str, run: dict) -> None:
    hub.emit_run_update(run_id, run)
    hub.emit_to_workflow(_workflow_id_from_run(run), "run_started", run=run)


def emit_node_started(
    run_id: str,
    *,
    node_id: str,
    node_type: str,
    node_label: str,
    started_at: str,
    config: dict | None = None,
    input: dict | None = None,
    variables: dict | None = None,
) -> None:
    hub.emit_node_started(
        run_id,
        node_id=node_id,
        node_type=node_type,
        node_label=node_label,
        started_at=started_at,
        config=config,
        input=input,
        variables=variables,
    )


def emit_node_log(run_id: str, log: dict) -> None:
    hub.emit_node_log(run_id, log)


def emit_run_finished(run_id: str, run: dict) -> None:
    hub.emit_run_finished(run_id, run)
    hub.emit_to_workflow(_workflow_id_from_run(run), "run_finished", run=run)
