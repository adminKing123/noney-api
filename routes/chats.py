from flask import Blueprint, request, jsonify
from middleware.auth import require_auth
from db import db
from ai import AIProvider
from ai.schema import TitleSummary
from config import CONFIG

chats_bp = Blueprint('chats', __name__)

@chats_bp.route("/delete_chat/<userId>/<chatId>", methods=["DELETE"])
@require_auth
def delete_chat(userId, chatId):
    db.chat.delete_chat(userId, chatId)
    return jsonify({
        "success": True,
        "message": "Chat and its subcollections deleted successfully!",
        "chatId": chatId
    })

@chats_bp.route("/rename_chat/<userId>/<chatId>", methods=["PUT"])
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

@chats_bp.route("/summarise_title", methods=["POST"])
@require_auth
def summarise_title():
    prompt = request.json.get("prompt", "")

    if not prompt:
        return jsonify({"error": "Prompt is required"}), 400

    summarise_prompt = f"Summarize this into a short title under 100 characters (only plain text):\n\n{prompt}"

    ai_provider = AIProvider()
    ai = ai_provider.get(CONFIG.MODELS.DEFAULT_MODEL)
    
    response = ai.with_structured_output(
        TitleSummary,
        method="json_schema"
    ).invoke(summarise_prompt)

    if not response or not response.title:
        return jsonify({"summarized_title": prompt[:24]})
    
    summary = response.title.strip()
    summary = summary[:100]

    return jsonify({"summarized_title": summary})
