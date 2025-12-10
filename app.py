from config import CONFIG
from flask import Flask, Response, request, jsonify
from flask_cors import CORS
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.messages import HumanMessage
import json
import uuid
import os
from firebase_admin import firestore
from firebase import db  # Firestore DB imported

# Set API key for LangChain Google Gemini
os.environ["GOOGLE_API_KEY"] = CONFIG["GOOGLE_API_KEY"]

app = Flask(__name__)
CORS(app)

# --- SSE Helpers ---
def send_event(event, data, is_json=True):
    if is_json:
        data = json.dumps(data)
    return f"event: {event}\ndata: {data}\n\n"

def send_step(data):
    return send_event("step", {"id": str(uuid.uuid4()), "data": data})

def send_start_step():
    return send_step([{"type": "connecting", "title": "Please Wait"}])

def send_end_step():
    return send_step([{"type": "finished", "title": "Finished"}])

def send_text(text, index=0):
    data = {
        "id": str(uuid.uuid4()),
        "data": text,
        "index": index,
    }
    return send_event("text", data)

# --- LangChain Gemini 2.5 Setup ---
gemini2_5_model = ChatGoogleGenerativeAI(model="gemini-2.5-flash")

# --- Generate Route ---
@app.route("/generate", methods=["POST"])
def stream():
    user_input = request.json.get("prompt", "")

    def generate():
        yield send_start_step()
        for chunk in gemini2_5_model.stream([HumanMessage(content=user_input)]):
            yield send_text(chunk.content)
        yield send_end_step()

    return Response(generate(), mimetype="text/event-stream")


# --- DELETE Chat Route ---
@app.route("/delete_chat/<userId>/<chatId>", methods=["DELETE"])
def delete_chat(userId, chatId):
    chat_ref = db.collection("users").document(userId).collection("chats").document(chatId)
    firestore.client().recursive_delete(chat_ref)

    chat_ref = db.collection("users").document(userId).collection("drafts").document(chatId)
    firestore.client().recursive_delete(chat_ref)

    return jsonify({
        "success": True,
        "message": "Chat and its subcollections deleted successfully!",
        "chatId": chatId
    })

@app.route("/summarise_title", methods=["POST"])
def summarise_title():
    prompt = request.json.get("prompt", "")

    if not prompt:
        return jsonify({"error": "Prompt is required"}), 400

    summarise_prompt = f"Summarize this into a short title under 100 characters:\n\n{prompt}"

    response = gemini2_5_model.invoke([HumanMessage(content=summarise_prompt)])
    summary = response.content.strip()

    # Ensure max 100 characters even if model exceeds
    summary = summary[:100]

    return jsonify({"summarized_title": summary})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))  # Render provides PORT
    app.run(host="0.0.0.0", port=port)

