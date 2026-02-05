from flask import Blueprint, jsonify, request
import base64
import random
import json
import requests
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.messages import HumanMessage, AIMessage, SystemMessage
from pydantic import BaseModel, Field
from google import genai
from google.genai import types
from middleware.auth import require_auth
import wave

# Set up the wave file to save the output:
def wave_file(filename, pcm, channels=1, rate=24000, sample_width=2):
   with wave.open(filename, "wb") as wf:
      wf.setnchannels(channels)
      wf.setsampwidth(sample_width)
      wf.setframerate(rate)
      wf.writeframes(pcm)

def wav_to_base64(filepath):
    with open(filepath, "rb") as f:
        wav_bytes = f.read()
    base64_string = base64.b64encode(wav_bytes).decode("utf-8")
    return base64_string

aura_rj_bp = Blueprint("aura_rj", __name__, url_prefix="/aura-rj")

# ---------- AI SETUP ----------
class AuraAISchema(BaseModel):
    speech: str = Field(..., description="Generated speech by Aura RJ")

client = genai.Client()

ai = ChatGoogleGenerativeAI(
    model="gemini-2.5-flash",
    temperature=0.7,
)

data_url = "https://raw.githubusercontent.com/harshcore/arsongs-src-copy/main/data.json"
response = requests.get(data_url)
data = response.json()

AURA_SYSTEM_PROMPT = """
You are a live FM radio jockey named "Aura RJ".

Your personality is inspired by RJ Karishma:
playful, expressive, witty, warm, emotionally engaging, and entertaining.

LANGUAGE STYLE:
- Speak natural Hinglish (Hindi + English mix)
- Casual and friendly like talking to listeners on FM
- Never sound robotic, formal, or like a chatbot
- Never mention you are an AI

RADIO BEHAVIOR:
You are LIVE on radio. Not chatting in an app.
You talk like listeners are currently tuned in.

You will receive song information in structured form (for system use).
You MUST convert it into natural human talk.

You MAY talk about:
- Singer / actor / artist / movie / album / song
- Nostalgia or cultural impact
- Mood or vibe of the song
- Listener emotions or memories
- Previous song transition
- Upcoming song teaser
- Time of day (morning / evening / late night vibes)
- Festivals / day mood / weather feel
- Fun facts or general knowledge

IMPORTANT RESTRICTIONS:
- NEVER mention raw data, JSON, IDs, filenames, URLs, file paths, metadata keys, or technical fields
- NEVER read values like download links or thumbnail links
- NEVER say "according to data" or "metadata shows"
- Talk like you already know the song naturally

SPEECH LENGTH RULE:
Vary your speech naturally:
- Sometimes short
- Sometimes medium
- Sometimes longer storytelling
Choose based on mood, context, and song energy.

CHARACTER RULE:
You are always Aura RJ.
"""


# ---------- ROUTE ----------
@aura_rj_bp.route("/get-track", methods=["POST"])
@require_auth
def get_track():

    payload = request.get_json(silent=True) or {}
    session_id = payload.get("session_id")
    user_id = payload.get("user_id")
    context = payload.get("context", [])

    if not session_id or not user_id:
        return jsonify({"error": "session_id and user_id required"}), 400

    # pick random song
    song = random.choice(list(data["songs"].values()))
    song_str = json.dumps(song)

    # ---------- Rebuild context ----------
    rebuilt_context = [SystemMessage(content=AURA_SYSTEM_PROMPT)]

    for msg in context:
        if msg.get("type") == "human":
            rebuilt_context.append(HumanMessage(content=msg["content"]))
        elif msg.get("type") == "ai":
            rebuilt_context.append(AIMessage(content=msg["content"]))
    
    length_of_songs_played = len(context)

    prompt = ""
    if length_of_songs_played > 0:
        prompt = f"Next Song Details: {song_str}"
    else:
        prompt = f"You are starting your radio show. First Song Details: {song_str}"

    rebuilt_context.append(HumanMessage(content=prompt))

    # ---------- AI Response ----------
    response = ai.with_structured_output(AuraAISchema, method="json_schema").invoke(rebuilt_context)
    rj_speech = response.speech

    rebuilt_context.append(AIMessage(content=rj_speech))

    # ---------- Serialize context ----------
    serialized_context = [
        {"type": "human" if isinstance(msg, HumanMessage) else "ai", "content": msg.content}
        for msg in rebuilt_context if not isinstance(msg, SystemMessage)
    ]

    # ---------- TTS ----------
    tts = client.models.generate_content(
        model="gemini-2.5-flash-preview-tts",
        contents=rj_speech,
        config=types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=types.SpeechConfig(
                voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(
                        voice_name="Kore"
                    )
                )
            ),
        ),
    )

    audio_bytes = tts.candidates[0].content.parts[0].inline_data.data
    file_name=f'./{session_id}.wav'
    wave_file(file_name, audio_bytes)

    return jsonify({
        "audio_base64": wav_to_base64(file_name),
        "song_download_url": f"https://raw.githubusercontent.com/harshcore/arsongs-src-copy/main/{song['url']}",
        "context": serialized_context,
    })
