"""
fuse/run_ws_server.py
=====================
Background WebSocket server for live Fuse run subscriptions.

Clients authenticate with a Firebase ID token, then receive a snapshot plus
streaming node/run events for a single run_id.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from typing import Any

import websockets
from websockets.server import WebSocketServerProtocol

from config import CONFIG
from fuse.run_events import hub

logger = logging.getLogger(__name__)

_server_thread: threading.Thread | None = None


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


_LIVE_PATH = "/fuse/runs/live"


async def _handle_client(websocket: WebSocketServerProtocol) -> None:
    path = getattr(getattr(websocket, "request", None), "path", "") or ""
    if path.rstrip("/") != _LIVE_PATH:
        await websocket.close(4004, "unknown path")
        return

    run_id: str | None = None
    try:
        raw = await asyncio.wait_for(websocket.recv(), timeout=30.0)
        msg = json.loads(raw)
        if msg.get("type") != "auth":
            await websocket.close(4001, "auth required")
            return

        token = msg.get("token")
        run_id = msg.get("run_id")
        if not token or not run_id:
            await websocket.close(4002, "missing token or run_id")
            return

        from db import db  # noqa: PLC0415 — lazy import

        try:
            user = db.user.authenticate(token)
        except Exception:
            await websocket.close(4003, "invalid token")
            return

        owner_id = user["uid"]
        run = db.workflow_run.get_run(run_id, owner_id)
        if run is None:
            await websocket.close(4004, "run not found")
            return

        logs = _fetch_all_logs(db, run_id, owner_id)
        snapshot = {
            "type": "snapshot",
            "run": run,
            "node_states": _node_states_from_logs(logs),
            "active_node_id": hub.get_active_node_id(run_id),
        }
        await websocket.send(json.dumps(snapshot, default=str))

        hub.subscribe(run_id, websocket)

        async for _message in websocket:
            # Client may send pings; ignore for now.
            pass
    except asyncio.TimeoutError:
        await websocket.close(4000, "auth timeout")
    except websockets.exceptions.ConnectionClosed:
        pass
    except Exception:
        logger.exception("[FUSE-WS] Client handler error")
    finally:
        if run_id:
            hub.unsubscribe(run_id, websocket)


async def _serve() -> None:
    hub.set_event_loop(asyncio.get_running_loop())
    host = CONFIG.FUSE_RUN_WS_HOST
    port = CONFIG.FUSE_RUN_WS_PORT
    logger.info("[FUSE-WS] Listening on ws://%s:%s", host, port)
    async with websockets.serve(
        _handle_client,
        host,
        port,
        ping_interval=20,
        ping_timeout=20,
        max_size=2**20,
    ):
        await asyncio.Future()


def start_run_ws_server() -> None:
    """Start the Fuse run WebSocket server in a daemon thread (idempotent)."""
    global _server_thread
    if _server_thread and _server_thread.is_alive():
        return

    def _run() -> None:
        try:
            asyncio.run(_serve())
        except Exception:
            logger.exception("[FUSE-WS] Server thread exited with error")

    _server_thread = threading.Thread(
        target=_run,
        name="fuse-run-ws",
        daemon=True,
    )
    _server_thread.start()
