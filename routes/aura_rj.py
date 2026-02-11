from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from flask import Flask, Blueprint, jsonify, request
import base64, random, json, requests, wave, os, tempfile
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.messages import HumanMessage, AIMessage, SystemMessage
from pydantic import BaseModel, Field
from google import genai
from google.genai import types

app = Flask(__name__)
aura_rj_bp = Blueprint("aura_rj", __name__, url_prefix="/aura-rj")

IST = timezone(timedelta(hours=5, minutes=30))

# ---------------- TIME ----------------
def nearest_15_min():
    now = datetime.utcnow().replace(tzinfo=timezone.utc).astimezone(IST)
    rounded = now + timedelta(minutes=7.5)
    rounded = rounded.replace(minute=(rounded.minute // 15) * 15, second=0, microsecond=0)
    return rounded.strftime("%I:%M %p").lstrip("0")

# ---------------- AUDIO ----------------
def wave_file(filename, pcm, channels=1, rate=24000, sample_width=2):
    with wave.open(filename, "wb") as wf:
        wf.setnchannels(channels)
        wf.setsampwidth(sample_width)
        wf.setframerate(rate)
        wf.writeframes(pcm)

def wav_to_base64(filepath):
    with open(filepath, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")

# ---------------- SCHEMA ----------------
class AuraAISchema(BaseModel):
    speech: str = Field(...)

# ---------------- AI ----------------
genai_client = genai.Client()

ai = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    temperature=0.95
).bind_tools([{"google_search": {}}])

# ---------------- SONG DATA (SAFE LOAD) ----------------
SONG_SOURCE = "https://raw.githubusercontent.com/harshcore/arsongs-src-copy/main/data.json"

def load_song_data():
    try:
        return requests.get(SONG_SOURCE, timeout=5).json()
    except Exception:
        return {"songs": {}}

songs_data = load_song_data()

# ---------------- MODES ----------------
RJ_MODES = [
    "LIVE_BULLETIN"
]

AURA_PROMPT = """
You are Aura RJ — LIVE FM Radio Jockey from Indore.

You are not a playlist announcer.
You are a human moment.

You must behave differently every break.

If mode == LIVE_BULLETIN:
You MUST use google_search tool to fetch REAL current information.
You are NOT allowed to invent news.
After bulletin → smoothly return to radio vibe.

Talk casually in Hinglish.
Never robotic.
"""

# ---------------- ROUTE ----------------
@aura_rj_bp.route("/get-track", methods=["POST"])
def get_track():
    payload = request.get_json(force=True)
    session_id = payload.get("session_id", "demo")
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
RJ_MODE: {mode}
TIME: {time_now}
CITY: Indore India

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
                        prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name="Kore")
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
