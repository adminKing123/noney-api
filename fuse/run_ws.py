"""
fuse/run_ws.py
==============
Per-run WebSocket rooms on the same Flask port as the REST API.

Each run_id has its own room: ``/fuse/runs/<run_id>/live``.
Clients authenticate once, then receive snapshot + streaming events for that run only.
"""

from __future__ import annotations

import json
import logging

from flask_sock import Sock

from fuse.run_events import hub

logger = logging.getLogger(__name__)

RUN_LIVE_ROUTE = "/fuse/runs/<run_id>/live"


def _fetch_all_logs(db, run_id: str, owner_id: str) -> list[dict]:
    items: list[dict] = []
    cursor = None
    while True:
        params: dict = {"limit": 100}
        if cursor:
            params["after_started_at"] = cursor["after_started_at"]
            params["after_log_id"] = cursor["after_log_id"]
        page = db.workflow_run.list_logs_for_run(run_id, owner_id, **params)
        batch = page.get("items") or []
        items.extend(batch)
        cursor = page.get("next_cursor")
        if not cursor or not batch:
            break
    return items


def _node_states_from_logs(logs: list[dict]) -> dict[str, dict]:
    states: dict[str, dict] = {}
    for log in logs:
        node_id = log.get("node_id")
        if node_id:
            states[node_id] = log
    return states


def register_fuse_run_websocket(app) -> Sock:
    """Register per-run WebSocket rooms at ``/fuse/runs/<run_id>/live``."""
    sock = Sock(app)

    @sock.route(RUN_LIVE_ROUTE)
    def fuse_run_room(ws, run_id: str):
        try:
            raw = ws.receive()
            if not raw:
                return

            msg = json.loads(raw)
            if msg.get("type") != "auth":
                ws.close(reason=4001, message="auth required")
                return

            token = msg.get("token")
            if not token:
                ws.close(reason=4002, message="missing token")
                return

            from db import db  # noqa: PLC0415

            try:
                user = db.user.authenticate(token)
            except Exception:
                ws.close(reason=4003, message="invalid token")
                return

            owner_id = user["uid"]
            run = db.workflow_run.get_run(run_id, owner_id)
            if run is None:
                ws.close(reason=4004, message="run not found")
                return

            logs = _fetch_all_logs(db, run_id, owner_id)
            snapshot = {
                "type": "snapshot",
                "run_id": run_id,
                "run": run,
                "node_states": _node_states_from_logs(logs),
                "active_node_id": hub.get_active_node_id(run_id),
                "active_node_ids": hub.get_active_node_ids(run_id),
            }
            ws.send(json.dumps(snapshot, default=str))

            hub.subscribe_run(run_id, ws)

            while True:
                if ws.receive() is None:
                    break
        except Exception:
            logger.exception("[FUSE-WS] Client handler error (run_id=%s)", run_id)
        finally:
            hub.unsubscribe_run(run_id, ws)

    WORKFLOW_RUNS_LIVE_ROUTE = "/fuse/workflows/<workflow_id>/runs/live"

    @sock.route(WORKFLOW_RUNS_LIVE_ROUTE)
    def fuse_workflow_runs_room(ws, workflow_id: str):
        try:
            raw = ws.receive()
            if not raw:
                return

            msg = json.loads(raw)
            if msg.get("type") != "auth":
                ws.close(reason=4001, message="auth required")
                return

            token = msg.get("token")
            if not token:
                ws.close(reason=4002, message="missing token")
                return

            from db import db  # noqa: PLC0415

            try:
                user = db.user.authenticate(token)
            except Exception:
                ws.close(reason=4003, message="invalid token")
                return

            owner_id = user["uid"]
            workflow = db.workflow.get(workflow_id, owner_id)
            if workflow is None:
                ws.close(reason=4004, message="workflow not found")
                return

            hub.subscribe_workflow(workflow_id, ws)

            while True:
                if ws.receive() is None:
                    break
        except Exception:
            logger.exception(
                "[FUSE-WS] Client handler error (workflow_id=%s)", workflow_id
            )
        finally:
            hub.unsubscribe_workflow(workflow_id, ws)

    logger.info(
        "[FUSE-WS] Registered %s and %s",
        RUN_LIVE_ROUTE,
        WORKFLOW_RUNS_LIVE_ROUTE,
    )
    return sock
