from flask import Blueprint, Response, request, abort
from middleware.auth import require_auth
from db import db
from ai import AIProvider
from config import CONFIG
import json

generation_bp = Blueprint('generation', __name__)

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

@generation_bp.route("/generate", methods=["POST"])
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
