from flask import Blueprint, request, jsonify, Response
from elevenlabs.client import ElevenLabs
from config import CONFIG
from middleware.auth import require_auth

tts_bp = Blueprint("tts", __name__, url_prefix="/tts")

# Initialise the ElevenLabs client once at module load time
_elevenlabs_client = ElevenLabs(api_key=CONFIG.ELEVENLABS_API_KEY)


@tts_bp.route("/speak", methods=["POST"])
@require_auth
def text_to_speech():
    """
    POST /tts/speak

    Request body (JSON):
        {
            "text":     "Hello, world!",          # required
            "voice_id": "<elevenlabs-voice-id>"   # optional, falls back to CONFIG default
        }

    Response:
        Binary MP3 audio stream (audio/mpeg).
    """
    body = request.get_json(silent=True)

    if not body or not body.get("text", "").strip():
        return jsonify({"error": "Field 'text' is required and must not be empty"}), 400

    text = body["text"].strip()
    voice_id = body.get("voice_id", CONFIG.ELEVENLABS_VOICE_ID)

    try:
        # text_to_speech.convert() returns an Iterator[bytes] in SDK v2.x
        audio_stream = _elevenlabs_client.text_to_speech.convert(
            voice_id=voice_id,
            text=text,
            model_id="eleven_multilingual_v2",
        )

        def generate_audio():
            for chunk in audio_stream:
                if chunk:
                    yield chunk

        return Response(
            generate_audio(),
            mimetype="audio/mpeg",
            headers={
                "Content-Disposition": "inline; filename=speech.mp3",
                "Transfer-Encoding": "chunked",
            },
        )

    except Exception as e:
        print(f"[TTS] ElevenLabs error: {e}")
        return jsonify({"error": "Failed to generate speech"}), 500
