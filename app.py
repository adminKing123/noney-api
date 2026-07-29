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


def _restore_active_workflows() -> None:
    """
    Re-register active Fuse workflow executions from Firestore after startup.

    Called once at module load time so that scheduled jobs resume and webhook
    look-ups work immediately after a server restart.
    """
    try:
        from db import db
        from fuse.runtime import runtime

        active = db.workflow.list_active()
        if active:
            logging.getLogger(__name__).info(
                "[FUSE] Restoring %d active workflow(s) from Firestore.", len(active)
            )
            runtime.restore_from_db(active)
    except Exception:
        logging.getLogger(__name__).warning(
            "[FUSE] Could not restore active workflows on startup (non-fatal).",
            exc_info=True,
        )


# _restore_active_workflows()


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port, debug=CONFIG.DEBUG)

