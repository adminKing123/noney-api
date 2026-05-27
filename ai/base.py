import uuid
from abc import ABC, abstractmethod
from .prompt_extensions import HTML_PREVIEW_EXTENSION, CHART_VIEW_EXTENSION

class BaseAI(ABC):
    """Base class every provider must follow."""

    def _build_system_prompt(self, payload, extra_parts=None):
        """Assemble the effective system prompt for a single request.

        Starts from the model's base system prompt (from config), appends any
        caller-supplied ``extra_parts`` (e.g. per-user context for HRMS), then
        appends output-mode extensions when the user has enabled them.

        Args:
            payload:     The raw request payload dict.
            extra_parts: Optional list of additional prompt strings to insert
                         between the base prompt and the output-mode extensions.
        """
        parts = [self.system_prompt] if self.system_prompt else []
        if extra_parts:
            parts.extend(extra_parts)
        if payload.get("generate_html"):
            parts.append(HTML_PREVIEW_EXTENSION)
        if payload.get("generate_charts"):
            parts.append(CHART_VIEW_EXTENSION)
        return "\n".join(parts) if parts else None

    def _event(self, event, data):
        return {
            "event": event,
            "data": data
        }

    def _step(self, data):
        return self._event("step", {"id": str(uuid.uuid4()), "data": data})
    
    def _source(self, data):
        return self._event("source", {"id": str(uuid.uuid4()), "data": data})

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
    
    def _send_generated_images(self, data, index=0):
        data = {
            "id": str(uuid.uuid4()),
            "data": data,
            "index": index,
        }
        return self._event("generated_images", data)
    
    def _interrupt(self, data):
        return self._event("interrupt", {"id": str(uuid.uuid4()), "data": data})
    
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
        return self._step([{
            "id": str(uuid.uuid4()),
            "title": f"Calling tool: {tool_name}",
            "tool_name": tool_name,
            "tool_args": tool_args,
            "type": "tool_call"
        }])
    
    def _tool_result(self, tool_id, tool_name, tool_result):
        return self._step([            {
            "id": str(uuid.uuid4()),
            "title": f"Tool result from: {tool_name}",
            "tool_id": tool_id,
            "tool_name": tool_name,
            "tool_result": tool_result,
            "type": "tool_result"
        }])

    @abstractmethod
    def stream(self, payload):
        """Return a generator that yields SSE responses"""
        pass

    @abstractmethod
    def invoke(self, payload):
        """Return a single response"""
        pass
