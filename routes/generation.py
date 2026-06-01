from flask import Blueprint, Response, request, abort, jsonify
from middleware.auth import require_auth
from db import db
from ai import AIProvider
from config import CONFIG
from utils.task_manager import task_manager, TaskStatus
from datetime import datetime, timezone
import json
import queue
import threading
import uuid

generation_bp = Blueprint('generation', __name__)


def run_generation_in_background(ai, payload, task, event_queue):
    msg = None
    action_type = payload.get("action_type", None)
    
    if action_type == "INTERRUPT_CONTINUE":
        msg = db.msg.get_msg_by_id(payload.get("chat_id"), payload.get("id"))
        if msg:
            msg.interrupt = payload.get("interrupt", None)
    else:
        msg = db.msg.get_new_msg(payload.get("id"), payload)
    
    if not msg:
        event_queue.put({"event": "error", "data": {"message": "Message not found"}})
        event_queue.put(None)
        task.status = TaskStatus.ERROR
        return
    
    task.status = TaskStatus.RUNNING
    
    try:
        for chunk in ai.stream(payload):
            if task.stop_requested:
                task.status = TaskStatus.STOPPED
                # Add stop step to message
                stop_step = {
                    "id": str(uuid.uuid4()),
                    "type": "stop",
                    "title": "Stopped"
                }
                msg.steps.append(stop_step)
                event_queue.put({"event": "step", "data": {"data": [stop_step], "id": stop_step["id"], "index": None}})
                event_queue.put({"event": "stopped", "data": {"reason": "user_requested"}})
                break
                
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
            elif eventtype == "usage":
                # Persist token counts and cost onto the message entity
                usage_data = eventdata or {}
                msg.tokens = {
                    "input": usage_data.get("input_tokens", 0),
                    "output": usage_data.get("output_tokens", 0),
                    "total": usage_data.get("total_tokens", 0),
                }
                msg.cost_usd = usage_data.get("cost_usd", 0.0)
                if usage_data.get("images_generated"):
                    msg.images_generated = usage_data.get("images_generated", 0)
            elif eventtype == "file":
                msg.answer_files.extend([eventdata])
            elif eventtype == "interrupt":
                msg.interrupt = eventdata
            else:
                if index is not None:
                    msg.answer[index] = {"id": eventid, "type": eventtype, "data": eventdata}

            event = {"event": eventtype, "data": data}
            task.add_event(event)
            
            try:
                event_queue.put_nowait(event)
            except queue.Full:
                pass
        
        if task.status == TaskStatus.RUNNING:
            task.status = TaskStatus.COMPLETED

        db.msg.save_message(payload.get("chat_id"), msg.get_dict())

        # Resolved model ID string (set by stream() before spawning this thread)
        resolved_model_id = payload.get("_model_id")

        # Update chat-level aggregate token/cost counters.
        # Pass the resolved string model ID, NOT msg.model which is the full dict.
        # Image generation models (Imagen 4, etc.) have zero tokens but non-zero
        # cost, so we guard on cost_usd > 0 as well as total_tokens > 0.
        has_tokens = msg.tokens and msg.tokens.get("total", 0) > 0
        has_cost   = (msg.cost_usd or 0.0) > 0
        if has_tokens or has_cost:
            db.chat.update_usage(
                payload.get("chat_id"),
                msg.tokens,
                msg.cost_usd or 0.0,
                model=resolved_model_id,
            )

            # Record into the user's persistent usage collection.
            # Structured as users/{uid}/usage/{chat_id}/messages/{msg_id}
            # so data survives chat deletion and mirrors the real collections.
            user_id = payload.get("user", {}).get("uid")
            if user_id:
                images_generated = getattr(msg, "images_generated", 0) or 0
                now_iso = datetime.now(timezone.utc).isoformat()
                db.analytics.record_generation(
                    user_id,
                    chat_id=payload.get("chat_id"),
                    message_id=payload.get("id"),
                    tokens=msg.tokens,
                    cost_usd=msg.cost_usd or 0.0,
                    model_id=resolved_model_id,
                    now_iso=now_iso,
                    images_generated=images_generated,
                    # Derive type from what was produced — extensible later
                    # for video ('video') and audio ('audio') routes.
                    generation_type="image" if images_generated > 0 else "text",
                )
        
    except Exception as e:
        print(e)
        task.status = TaskStatus.ERROR
        task.error = str(e)
        
        error_step = {
            "id": str(uuid.uuid4()),
            "type": "error",
            "title": "Error",
            "message": str(e)
        }
        msg.steps.append(error_step)
        try:
            event_queue.put_nowait({"event": "step", "data": {"data": [error_step], "id": error_step["id"], "index": None}})
            event_queue.put_nowait({"event": "error", "data": {"message": str(e)}})
        except queue.Full:
            pass

        db.msg.save_message(payload.get("chat_id"), msg.get_dict())
    
    finally:
        try:
            event_queue.put_nowait(None)
        except queue.Full:
            pass


def stream_events(event_queue, task):
    try:
        while True:
            event = event_queue.get()
            
            if event is None:
                yield f"event: end\ndata: {json.dumps({'status': task.status.value})}\n\n"
                break
            
            eventtype = event.get("event")
            data = event.get("data")
            yield f"event: {eventtype}\ndata: {json.dumps(data)}\n\n"
    except GeneratorExit:
        pass


@generation_bp.route("/generate", methods=["POST"])
@require_auth
def stream():
    payload = request.json or {}
    model = payload.get("model", {})
    model_id = model.get("id", CONFIG.MODELS.DEFAULT_MODEL)
    message_id = payload.get("id")
    chat_id = payload.get("chat_id")
    
    if not message_id or not chat_id:
        abort(400, description="Message ID and Chat ID are required")
    
    payload["user"] = request.user
    user_id = request.user.get("uid", "unknown")
    # Inject the resolved model ID string so the background thread can use it
    # directly without having to unpack the model dict again.
    payload["_model_id"] = model_id
    
    existing_task = task_manager.get_task_by_message_id(message_id)
    if existing_task and existing_task.status == TaskStatus.RUNNING:
        return jsonify({
            "success": False,
            "message": "Generation already in progress",
            "task": existing_task.to_dict()
        }), 409
    
    ai_provider = AIProvider()
    ai = ai_provider.get(model_id)
    
    task = task_manager.create_task(message_id, chat_id, user_id)
    
    event_queue = queue.Queue(maxsize=1000)
    
    gen_thread = threading.Thread(
        target=run_generation_in_background,
        args=(ai, payload, task, event_queue),
        daemon=True
    )
    gen_thread.start()
    task.thread = gen_thread
    
    return Response(
        stream_events(event_queue, task),
        mimetype="text/event-stream",
        headers={"X-Task-ID": task.task_id}
    )


@generation_bp.route("/generate/stop/<message_id>", methods=["POST"])
@require_auth
def stop_generation(message_id):
    task = task_manager.get_task_by_message_id(message_id)
    
    if not task:
        return jsonify({
            "success": False,
            "message": "No active generation found for this message"
        }), 404
    
    if task.status != TaskStatus.RUNNING:
        return jsonify({
            "success": False,
            "message": f"Task is not running (status: {task.status.value})"
        }), 400
    
    success = task_manager.stop_task(message_id)
    
    return jsonify({
        "success": success,
        "message": "Stop requested" if success else "Failed to stop task",
        "task": task.to_dict()
    })
