import logging

import requests
from flask import Blueprint, jsonify, request

from config import CONFIG
from middleware.auth import require_auth

stt_bp = Blueprint("stt", __name__, url_prefix="/stt")

DEEPGRAM_LISTEN_WS = "wss://api.deepgram.com/v1/listen"
DEEPGRAM_LISTEN_HTTP = "https://api.deepgram.com/v1/listen"

_logger = logging.getLogger(__name__)


def _deepgram_not_configured():
    if CONFIG.DEEPGRAM_API_KEY:
        return None
    return jsonify({"error": "Deepgram is not configured on the server"}), 503


@stt_bp.route("/deepgram/live-config", methods=["GET"])
@require_auth
def deepgram_live_config():
    """
    GET /stt/deepgram/live-config

    Returns WebSocket URL, auth token, and query params for live streaming STT.
    The token is the server-side API key — only issued to authenticated users.
    """
    missing = _deepgram_not_configured()
    if missing:
        return missing

    language = request.args.get("language", CONFIG.DEEPGRAM_LANGUAGE)
    model = request.args.get("model", CONFIG.DEEPGRAM_MODEL)

    return jsonify(
        {
            "listenUrl": DEEPGRAM_LISTEN_WS,
            "token": CONFIG.DEEPGRAM_API_KEY,
            "params": {
                "model": model,
                "language": language,
                "smart_format": "true",
                "interim_results": "true",
                "punctuate": "true",
                "encoding": "linear16",
                "sample_rate": str(CONFIG.DEEPGRAM_SAMPLE_RATE),
                "channels": "1",
            },
        }
    )


@stt_bp.route("/deepgram/transcribe", methods=["POST"])
@require_auth
def deepgram_transcribe():
    """
    POST /stt/deepgram/transcribe

    Proxies pre-recorded audio to Deepgram's REST listen API (keeps API key server-side).
    Body: raw audio bytes (e.g. audio/wav). Optional query: sample_rate, model.
    """
    missing = _deepgram_not_configured()
    if missing:
        return missing

    audio = request.get_data()
    if not audio:
        return jsonify({"error": "Request body must contain audio data"}), 400

    sample_rate = request.args.get("sample_rate", str(CONFIG.DEEPGRAM_SAMPLE_RATE))
    model = request.args.get("model", CONFIG.DEEPGRAM_MODEL)
    content_type = request.content_type or "audio/wav"

    params = {
        "model": model,
        "smart_format": "true",
        "encoding": "linear16",
        "sample_rate": sample_rate,
        "channels": "1",
    }

    try:
        response = requests.post(
            DEEPGRAM_LISTEN_HTTP,
            params=params,
            headers={
                "Authorization": f"Token {CONFIG.DEEPGRAM_API_KEY}",
                "Content-Type": content_type,
            },
            data=audio,
            timeout=120,
        )
    except requests.RequestException as exc:
        _logger.exception("[STT] Deepgram request failed")
        return jsonify({"error": "Failed to reach Deepgram"}), 502

    if not response.ok:
        _logger.warning(
            "[STT] Deepgram error %s: %s",
            response.status_code,
            response.text[:500],
        )
        return jsonify({"error": "Transcription failed", "details": response.text}), response.status_code

    try:
        payload = response.json()
    except ValueError:
        return jsonify({"error": "Invalid response from Deepgram"}), 502

    transcript = (
        payload.get("results", {})
        .get("channels", [{}])[0]
        .get("alternatives", [{}])[0]
        .get("transcript", "")
    )

    return jsonify({"transcript": transcript.strip(), "raw": payload})
