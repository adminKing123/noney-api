from flask import Blueprint, jsonify
from google import genai
import datetime
from config import CONFIG
from middleware.auth import require_auth

aura_voice_bp = Blueprint("aura_voice", __name__, url_prefix="/aura-voice")

client = genai.Client(
    api_key=CONFIG.GOOGLE_API_KEY,
    http_options={"api_version": "v1alpha"}
)

@aura_voice_bp.route("/get/session-id", methods=["GET"])
@require_auth
def get_session_id():
    try:
        now = datetime.datetime.now(tz=datetime.timezone.utc)

        token = client.auth_tokens.create(
            config={
                "uses": 1,
                "expire_time": now + datetime.timedelta(minutes=30),
                "new_session_expire_time": now + datetime.timedelta(minutes=1),
                'http_options': {'api_version': 'v1alpha'},
            }
        )

        # IMPORTANT: frontend needs token.name
        return jsonify({
            "name": token.name,
        }), 200

    except Exception as e:
        print("Token error:", str(e))
        return jsonify({"error": "Failed to create session"}), 500
