from config import CONFIG
from flask import Flask, Response, request, jsonify, send_from_directory, abort
from flask_cors import CORS
import os
from db import db
from ai import AIProvider
from middleware.auth import require_auth
from utils.files import save_file

app = Flask(__name__)
CORS(app)

@app.route("/generate", methods=["POST"])
@require_auth
def stream():
    model_id = request.json.get("model_id", CONFIG.MODELS.DEFAULT_MODEL)
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

@app.route("/upload_file", methods=["POST"])
@require_auth
def upload_file():
    user_id = request.user.get("user_id", None)
    chat_id = request.form.get("chat_id")
    file_id = request.form.get("file_id")

    if not chat_id or not user_id or not file_id:
        return jsonify({"error": "chat_id, user_id, and file_id are required"}), 400

    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["file"]

    if file.filename == "":
        return jsonify({"error": "Empty filename"}), 400

    file_meta = save_file(file, user_id, file_id)

    return jsonify(file_meta), 201

@app.route("/delete_file/<filename>", methods=["DELETE"])
@require_auth
def delete_file(filename):
    upload_dir = CONFIG.UPLOADS.UPLOAD_FOLDER
    file_path = os.path.join(upload_dir, filename)

    if not os.path.exists(file_path):
        return jsonify({"error": "File not found"}), 404

    os.remove(file_path)
    return jsonify({"success": True, "message": "File deleted successfully"}), 200

@app.route("/uploads/<filename>", methods=["GET"])
def download_file(filename):
    upload_dir = CONFIG.UPLOADS.UPLOAD_FOLDER
    file_path = os.path.join(upload_dir, filename)

    if not os.path.exists(file_path):
        abort(404)

    return send_from_directory(
        upload_dir,
        filename,
        as_attachment=True
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))  # Render provides PORT
    app.run(host="0.0.0.0", port=port, debug=CONFIG.DEBUG)

