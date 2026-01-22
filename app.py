from config import CONFIG
from flask import Flask, Response, request, jsonify, send_from_directory, abort
from flask_cors import CORS
import os
from db import db
from ai import AIProvider
from middleware.auth import require_auth
import json

app = Flask(__name__)
CORS(app)

def stream_generator(ai, payload):
    msg = None
    action_type = payload.get("action_type", None)
    
    if action_type == "INTERRUPT_CONTINUE":
        msg = db.msg.get_msg_by_id(payload.get("chat_id"), payload.get("id"))
        msg.interrupt = payload.get("interrupt", None)
    else:
        msg = db.msg.get_new_msg(payload.get("id"), payload)
    
    if not msg:
        abort(404, description="Message not found")
    for chunk in ai.stream(payload):
        eventtype = chunk.get("event")
        data = chunk.get("data")

        eventdata = data.get("data", None)
        eventid = data.get("id", None)
        index = data.get("index", None)

        if eventtype == "text":
            if index < len(msg.answer):
                msg.answer[index]["data"] += eventdata or ""
            elif index == len(msg.answer):
                msg.answer.append({"id": eventid, "type": "text", "data": eventdata or ""})
        elif eventtype == "generated_images":
            if index < len(msg.answer):
                msg.answer[index]["data"] += eventdata or []
            elif index == len(msg.answer):
                msg.answer.append({"id": eventid, "type": "generated_images", "data": eventdata or []})
        elif eventtype == "step":
            msg.steps.extend(eventdata)
        elif eventtype == "source":
            msg.sources.extend(eventdata)
        elif eventtype == "duration":
            msg.duration = eventdata.get("seconds", None)
        elif eventtype == "file":
            msg.answer_files.extend([
                eventdata,
            ])
        elif eventtype == "interrupt":
            msg.interrupt = eventdata
        else:
            msg.answer[index] = {"id": eventid, "type": eventtype, "data": eventdata}

        yield f"event: {eventtype}\ndata: {json.dumps(data)}\n\n"
    
    db.msg.save_message(payload.get("chat_id"), msg.get_dict())

@app.route("/generate", methods=["POST"])
@require_auth
def stream():
    payload = request.json or {}
    model = payload.get("model", {})
    model_id = model.get("id", CONFIG.MODELS.DEFAULT_MODEL)
    
    payload["user"] = request.user
    ai_provider = AIProvider()
    ai = ai_provider.get(model_id)
    return Response(
        stream_generator(ai, payload),
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

