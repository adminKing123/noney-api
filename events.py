import json
import uuid

def send_event(event, data, is_json=True):
    if is_json: data = json.dumps(data)
    return f"event: {event}\ndata: {data}\n\n"

def send_step(data):
    return send_event("step", {"id": str(uuid.uuid4()), "data": data})

def send_start_step():
    return send_step([{"type": "connecting", "title": "Please Wait",}])

def send_end_step():
    return send_step([{"type": "finished", "title": f"Finished",}])

def send_searching_event(title, description=""):
    return send_step([{"type": "searching", "title": title, "description": description}])

def send_text(text, index=0):
    data = {
        "id": str(uuid.uuid4()),
        "data": text,
        "index": index,
    }
    return send_event("text", data)