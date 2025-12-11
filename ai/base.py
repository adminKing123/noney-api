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
        return self._step([{"type": "connecting", "title": "Thinking"}])

    def _started(self):
        return self._step([{"type": "started", "title": "Generating"}])

    def _end(self):
        return self._step([{"type": "finished", "title": "Finished"}])
    
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

    def _send_duration(self, seconds):
        return self._event("duration", {
            "data": {
                "seconds": seconds
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
