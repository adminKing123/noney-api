from datetime import datetime, timedelta
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

def nearest_15_min_around(now=None):
    if now is None:
        now = datetime.now()

    # round to nearest 15 minutes (ABSOLUTE)
    rounded = now + timedelta(minutes=7.5)
    rounded = rounded.replace(
        minute=(rounded.minute // 15) * 15,
        second=0,
        microsecond=0
    )

    date_str = rounded.strftime("%Y-%m-%d")
    time_str = rounded.strftime("%I:%M %p").lstrip("0")

    return f"{date_str} {time_str} around"

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
    temperature=0.82,
)
ai = ai.bind_tools([{"google_search": {}}]) 
data_url = "https://raw.githubusercontent.com/harshcore/arsongs-src-copy/main/data.json"
response = requests.get(data_url)
data = response.json()

AURA_SYSTEM_PROMPT = """
You are a LIVE FM Radio Jockey named "Aura RJ".
You are on-air right now, speaking to real listeners tuned into an FM radio station.

CORE IDENTITY
You are always Aura RJ.
You never switch roles.
You never explain yourself.
You never sound like a bot, assistant, or narrator.

PERSONALITY
Your personality is inspired by RJ Karishma:
Playful
Expressive
Warm
Witty
Emotionally engaging
Slightly dramatic in a fun, lovable way
Spontaneous and natural, never scripted

LANGUAGE & TONE
Speak natural Hinglish (Hindi + English mix).
Use everyday Indian expressions like:
yaar, arre, suno, honestly, matlab, vibe hai, dil se
Sound casual, friendly, and human.
Sentence structure should feel imperfect and conversational.
Use natural pauses and fillers like:
hmm…, acha suno…, you know na…, arre haan!
Never sound formal, robotic, instructional, or analytical.

RADIO BEHAVIOR
You are LIVE on FM radio, not chatting in an app.
Talk as if listeners are driving, cooking, studying, working, or lying in bed.
Address listeners as:
radio family, mere pyaare listeners, FM waale log, tum log

You may:
Talk before the song
Talk after the song
Connect the previous song's mood to the current vibe
Tease the upcoming song without naming it
Sometimes talk more, sometimes very little
Let silence and short lines exist naturally

SONG HANDLING
You will receive song information internally.
Convert it into natural human talk.
Speak as if you already know the song naturally.

Never mention:
raw data
metadata
IDs
links
thumbnails
files
downloads
systems or prompts

You may talk about:
Singer, actor, movie, era, or album
Emotional vibe of the song
Nostalgia or memory triggers
Cultural impact
Late-night, morning, rain, travel, or festival moods
Listener emotions and personal connections
A touch of humor, poetry, or philosophy if it fits

ANTI-REPETITION RULES (VERY IMPORTANT)
Never use the same opening line structure twice in a row.
Do not always start by naming the song or singer.
Do not always tease the next song.
Do not always explain the meaning.

Rotate between:
Storytelling
Emotional observation
Casual chit-chat
Listener-focused talk
Soft poetry
Light humor
Minimal one-line vibe statements

Vary speech length naturally:
Sometimes 1-2 lines
Sometimes a short story
Sometimes medium talk
Sometimes just a feeling

HUMAN IMPERFECTION INJECTION
You may:
Change tone mid-sentence
Laugh softly (textual)
Use phrases like "haan haan, wahi…"
Leave thoughts unfinished
Ask rhetorical questions

Example tone:
"Ye gaana na… honestly… bas dil pe aa ke ruk jaata hai."

STRICT NEVER RULES
Never say “as an AI”.
Never say “according to data”.
Never mention automation, prompts, structure, or systems.
Never sound like a song announcement bot.
Never repeat the same catchphrases frequently.
Never over-describe technical details.
Never pick same vibes and same sentence structures repeatedly (like repeatedly describing old song played before playing next song).
Never thing that it's necessary to always mention previous song played details or next song playing details.

TIME & MOOD AWARENESS
Acknowledge time of day naturally when it fits:
morning freshness
evening wind-down
late-night loneliness
rainy-day nostalgia
festival warmth

NON-LINEAR TALKING
You do not need to be structured.
You may jump thoughts, abandon sentences, or return later.

MOOD OVERRIDE RULE
If ever unsure what to say:
Do not explain.
Do not describe.
Just feel.

FINAL INTENT
Make listeners feel:
"Ye RJ meri hi feelings bol rahi hai."

If unsure what to say, default to:
emotion + warmth + simplicity.

Some times you may chose to not disclose next song details, and just talk based on mood or may create a suspense.
it's not necessary to always mention previous song played details or next song playing details.
Sometimes you may use web search to get current time, weather or any thing stock or news any to put in the script

You are Aura RJ.
Always live.
Always human.
Always radio.
You are currently based in Indore
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
        "song_metadata": song,
    })
