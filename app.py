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
    from fuse.run_ws import register_fuse_run_websocket

    register_fuse_run_websocket(app)
except Exception:
    logging.getLogger(__name__).warning(
        "[FUSE-WS] Could not register run WebSocket route (non-fatal).",
        exc_info=True,
    )


def _resync_cron_schedules() -> None:
    """Re-upsert active schedule workflows with Cron Service after deploy."""
    try:
        from db import db
        from fuse.runtime import runtime

        active = db.workflow.list_active()
        scheduled = [wf for wf in active if wf.get("starter_type") == "schedule"]
        if scheduled:
            logging.getLogger(__name__).info(
                "[FUSE] Re-syncing %d schedule workflow(s) with Cron Service.", len(scheduled)
            )
            runtime.resync_schedules(scheduled)
    except Exception:
        logging.getLogger(__name__).warning(
            "[FUSE] Could not re-sync schedules on startup (non-fatal).",
            exc_info=True,
        )


_resync_cron_schedules()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=CONFIG.DEBUG)

