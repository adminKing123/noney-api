from flask import Blueprint, jsonify
from db.datacontroller import db
from utils.email_service import is_email_service_configured

health_bp = Blueprint('health', __name__)

@health_bp.route("/health", methods=["GET"])
def health_check():
    try:
        # Check if database is accessible
        db.client.collection("system").document("health").get()
        db_status = "ok"
    except Exception:
        db_status = "error"

    status_code = 200 if db_status == "ok" else 500
    return jsonify({
        "status": "ok",
        "database": db_status,
        "email_service_configured": is_email_service_configured(),
    }), status_code
