from config import CONFIG
from flask import Flask, Response, request, jsonify, send_from_directory, abort
from flask_cors import CORS
import os
from db import db
from ai import AIProvider
from middleware.auth import require_auth
from utils.files import save_file, remove_file

app = Flask(__name__)
CORS(app)

@app.route("/generate", methods=["POST"])
@require_auth
def stream():
    model_id = request.json.get("model_id", CONFIG.MODELS.DEFAULT_MODEL)
    prompt = request.json.get("prompt", "")
    chat_uid = request.json.get("chat_uid", None)
    descisions = request.json.get("descisions", None)
    ai_provider = AIProvider()
    ai = ai_provider.get(model_id)
    return Response(
        ai.stream({
            "prompt": prompt,
            "chat_uid": chat_uid,
            "user": request.user,
            "descisions": descisions,
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

@app.route("/rename_chat/<userId>/<chatId>", methods=["PUT"])
@require_auth
def rename_chat(userId, chatId):
    new_title = request.json.get("title", "")
    
    if not new_title:
        return jsonify({"error": "Title is required"}), 400
    
    db.chat.rename_chat(userId, chatId, new_title)
    return jsonify({
        "success": True,
        "message": "Chat renamed successfully!",
        "chatId": chatId,
        "title": new_title
    })

@app.route("/summarise_title", methods=["POST"])
@require_auth
def summarise_title():
    prompt = request.json.get("prompt", "")

    if not prompt:
        return jsonify({"error": "Prompt is required"}), 400

    summarise_prompt = f"Summarize this into a short title under 100 characters (only plain text):\n\n{prompt}"
    ai_provider = AIProvider()
    ai = ai_provider.get(CONFIG.MODELS.DEFAULT_MODEL)
    response = ai.invoke({
        "prompt": summarise_prompt,
        "user": request.user
    })
    summary = response.content.strip()

    # Ensure max 100 characters even if model exceeds
    summary = summary[:100]

    return jsonify({"summarized_title": summary})

@app.route("/health", methods=["GET"])
def health_check():
    return jsonify({"status": "ok"}), 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))  # Render provides PORT
    app.run(host="0.0.0.0", port=port, debug=CONFIG.DEBUG)

