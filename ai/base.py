import uuid
import json
from abc import ABC, abstractmethod

class BaseAI(ABC):
    """Base class every provider must follow."""

    def _event(self, event, data):
        return f"event: {event}\ndata: {json.dumps(data)}\n\n"

    def _step(self, data):
        return self._event("step", {"id": str(uuid.uuid4()), "data": data})

    def _start(self):
        return self._step([{"id": str(uuid.uuid4()), "type": "connecting", "title": "Thinking"}])

    def _started(self):
        return self._step([{"id": str(uuid.uuid4()), "type": "started", "title": "Generating"}])

    def _end(self):
        return self._step([{"id": str(uuid.uuid4()), "type": "finished", "title": "Finished"}])
    
    def _send_step(self, type, title, detail=None):
        data = {"type": type, "title": title}
        if detail:
            data["detail"] = detail
        return self._step([data])

    def _text(self, text, index=0):
        data = {
            "id": str(uuid.uuid4()),
            "data": text,
            "index": index,
        }
        return self._event("text", data)
    
    def _file(self, data):
        data = {
            "id": str(uuid.uuid4()),
            "data": data,
        }
        return self._event("file", data)

    def _send_duration(self, seconds):
        return self._event("duration", {
            "data": {
                "seconds": seconds
            }
        })
    
    def _tool_call(self, tool_name, tool_args):
        return self._event("step", {
            "data": {
                "id": str(uuid.uuid4()),
                "title": f"Calling tool: {tool_name}",
                "tool_name": tool_name,
                "tool_args": tool_args,
                "type": "tool_call"
            }
        })
    
    def _tool_result(self, tool_id, tool_name, tool_result):
        return self._event("step", {
            "data": {
                "id": str(uuid.uuid4()),
                "title": f"Tool result from: {tool_name}",
                "tool_id": tool_id,
                "tool_name": tool_name,
                "tool_result": tool_result,
                "type": "tool_result"
            }
        })

    @abstractmethod
    def stream(self, payload):
        """Return a generator that yields SSE responses"""
        pass

    @abstractmethod
    def invoke(self, payload):
        """Return a single response"""
        pass
