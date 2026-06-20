import json
import os
import random
import tempfile
from flask import jsonify, request
from google.genai import types
from langchain.messages import AIMessage, HumanMessage, SystemMessage

from .config import AURA_PROMPT, RJ_MODES, AuraAISchema, ai, genai_client, songs_data
from .utils import nearest_15_min, wave_file, wav_to_base64
from . import aura_rj_bp

# ---------------- ROUTE ----------------
@aura_rj_bp.route("/get-track", methods=["POST"])
def get_track():
    payload = request.get_json(force=True)
    context = payload.get("context", [])

    if not songs_data.get("songs"):
        return jsonify({"error": "Song database unavailable"}), 500

    song = random.choice(list(songs_data["songs"].values()))
    mode = random.choice(RJ_MODES)
    time_now = nearest_15_min()

    rebuilt_context = [SystemMessage(content=AURA_PROMPT)]

    for msg in context:
        if msg["type"] == "human":
            rebuilt_context.append(HumanMessage(content=msg["content"]))
        else:
            rebuilt_context.append(AIMessage(content=msg["content"]))

    human_prompt = f"""
RJ_MODE: {mode} (You must Not add to speech)
TIME: {time_now} (Not required to add to speech everytime, add time in your speech sometimes to make it more real but not always, use it creatively and naturally)
CITY: Indore India (Not required to add to speech everytime, add city in your speech sometimes to make it more real but not always, use it creatively and naturally)

Please also check your previous messages and your speech should not look repetitive to what you have said before in this session.

{"This is the starting of the radio" if len(context) == 0 else ""}

Next Song You Playing {json.dumps(song)}
"""

    rebuilt_context.append(HumanMessage(content=human_prompt))

    try:
        response = ai.with_structured_output(AuraAISchema, method="json_schema").invoke(rebuilt_context)
        speech = response.speech
    except Exception as e:
        return jsonify({"error": "AI generation failed"}), 500

    rebuilt_context.append(AIMessage(content=speech))

    serialized_context = [
        {"type": "human" if isinstance(m, HumanMessage) else "ai", "content": m.content}
        for m in rebuilt_context if not isinstance(m, SystemMessage)
    ]

    # ---------------- TTS + SAFE TEMP FILE ----------------
    temp_file = None
    try:
        tts = genai_client.models.generate_content(
            model="gemini-2.5-flash-preview-tts",
            contents=speech,
            config=types.GenerateContentConfig(
                response_modalities=["AUDIO"],
                speech_config=types.SpeechConfig(
                    voice_config=types.VoiceConfig(
                        # prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Kore")
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Laomedeia")
                    )
                ),
            ),
        )

        audio_bytes = tts.candidates[0].content.parts[0].inline_data.data

        # create temp file safely
        with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as tmp:
            temp_file = tmp.name

        wave_file(temp_file, audio_bytes)
        audio_b64 = wav_to_base64(temp_file)

    finally:
        # ALWAYS delete file even if crash
        if temp_file and os.path.exists(temp_file):
            os.remove(temp_file)

    return jsonify({
        "audio_base64": audio_b64,
        "song_download_url": f"https://raw.githubusercontent.com/harshcore/arsongs-src-copy/main/{song['url']}",
        "context": serialized_context,
        "song_metadata": song,
    })
