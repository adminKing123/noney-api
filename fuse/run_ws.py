"""
fuse/run_ws.py
==============
Fuse run live WebSocket on the same Flask port as the REST API (Render-safe).
"""

from __future__ import annotations

import json
import logging

from flask_sock import Sock

from fuse.run_events import hub

logger = logging.getLogger(__name__)

LIVE_PATH = "/fuse/runs/live"


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
    """Attach ``GET ws://<same-host>/fuse/runs/live`` to the Flask app."""
    sock = Sock(app)

    @sock.route(LIVE_PATH)
    def fuse_runs_live(ws):
        run_id: str | None = None
        try:
            raw = ws.receive()
            if not raw:
                return

            msg = json.loads(raw)
            if msg.get("type") != "auth":
                ws.close(reason=4001, message="auth required")
                return

            token = msg.get("token")
            run_id = msg.get("run_id")
            if not token or not run_id:
                ws.close(reason=4002, message="missing token or run_id")
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
                "run": run,
                "node_states": _node_states_from_logs(logs),
                "active_node_id": hub.get_active_node_id(run_id),
            }
            ws.send(json.dumps(snapshot, default=str))

            hub.subscribe(run_id, ws)

            while True:
                if ws.receive() is None:
                    break
        except Exception:
            logger.exception("[FUSE-WS] Client handler error")
        finally:
            if run_id:
                hub.unsubscribe(run_id, ws)

    logger.info("[FUSE-WS] Registered WebSocket route %s (same port as Flask)", LIVE_PATH)
    return sock
