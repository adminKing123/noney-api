from config import CONFIG
from flask import Flask, Response, request, jsonify
from flask_cors import CORS
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain.messages import HumanMessage
# import json
# import uuid
import os
# from firebase_admin import firestore
# from firebase import db
from db import db
from ai import AIProvider, Models
from middleware.auth import require_auth

app = Flask(__name__)
CORS(app)

@app.route("/generate", methods=["POST"])
@require_auth
def stream():
    model_id = request.json.get("model_id", Models.DEFAULT_MODEL)
    prompt = request.json.get("prompt", "")
    chat_uid = request.json.get("chat_uid", None)
    ai_provider = AIProvider()
    ai = ai_provider.get(model_id)
    return Response(
        ai.stream({
            "prompt": prompt,
            "chat_uid": chat_uid,
            "user": request.user,
        }),
        mimetype="text/event-stream"
    )

# --- DELETE Chat Route ---
@app.route("/delete_chat/<userId>/<chatId>", methods=["DELETE"])
@require_auth
def delete_chat(userId, chatId):
    db.chat.delete_chat(userId, chatId)
    return jsonify({
        "success": True,
        "message": "Chat and its subcollections deleted successfully!",
        "chatId": chatId
    })

@app.route("/summarise_title", methods=["POST"])
@require_auth
def summarise_title():
    prompt = request.json.get("prompt", "")

    if not prompt:
        return jsonify({"error": "Prompt is required"}), 400

    summarise_prompt = f"Summarize this into a short title under 100 characters:\n\n{prompt}"
    ai_provider = AIProvider()
    ai = ai_provider.get(Models.DEFAULT_MODEL)
    response = ai.invoke({
        "prompt": summarise_prompt,
        "user": request.user
    })
    summary = response.content.strip()

    # Ensure max 100 characters even if model exceeds
    summary = summary[:100]

    return jsonify({"summarized_title": summary})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))  # Render provides PORT
    app.run(host="0.0.0.0", port=port, debug=CONFIG.DEBUG)

