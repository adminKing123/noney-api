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
        return self._step([{"type": "connecting", "title": "Please Wait"}])

    def _end(self):
        return self._step([{"type": "finished", "title": "Finished"}])

    def _text(self, text, index=0):
        data = {
            "id": str(uuid.uuid4()),
            "data": text,
            "index": index,
        }
        return self._event("text", data)

    @abstractmethod
    def stream(self, messages):
        """Return a generator that yields SSE responses"""
        pass

    @abstractmethod
    def invoke(self, messages):
        """Return a single response"""
        pass
