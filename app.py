import logging
import os

from config import CONFIG
from flask import Flask
from flask_cors import CORS
from routes import register_blueprints

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

app = Flask(__name__)
CORS(app)

register_blueprints(app)

try:
    from fuse.run_ws_server import start_run_ws_server

    start_run_ws_server()
except Exception:
    logging.getLogger(__name__).warning(
        "[FUSE-WS] Could not start run WebSocket server (non-fatal).",
        exc_info=True,
    )


def _restore_scheduled_workflows() -> None:
    """
    Re-register scheduled Fuse workflows from Firestore after startup.

    Webhook, Webex message, and GitHub PR workflows resolve lazily on the first
    incoming trigger via ``runtime.resolve_execution()`` — they do not need a
    startup restore because their compiled graph and external webhook metadata
    are already persisted in Firestore.

    Schedule workflows still need this because APScheduler jobs are process-local.
    """
    try:
        from db import db
        from fuse.runtime import runtime

        active = db.workflow.list_active()
        scheduled = [
            wf for wf in active
            if (wf.get("compiled_graph") or {}).get("starter", {}).get("node_type") == "schedule"
        ]
        if scheduled:
            logging.getLogger(__name__).info(
                "[FUSE] Restoring %d scheduled workflow(s) from Firestore.", len(scheduled)
            )
            runtime.restore_from_db(scheduled)
    except Exception:
        logging.getLogger(__name__).warning(
            "[FUSE] Could not restore scheduled workflows on startup (non-fatal).",
            exc_info=True,
        )


# Uncomment when schedule nodes are in use:
# _restore_scheduled_workflows()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=CONFIG.DEBUG)

