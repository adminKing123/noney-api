from db import db
from functools import lru_cache
from langchain.messages import HumanMessage, AIMessage, SystemMessage, ToolMessage
from config import CONFIG

class HrmsContext:
    MESSAGES_LIMIT = CONFIG.GEMINI_MESSAGE_LIMIT

    def __init__(self, user_id, chat_uid, system_prompt=None):
        self.user_id = user_id
        self.chat_uid = chat_uid
        self.system_prompt = system_prompt
        self.messages = list(self._get_messages())

    def _get_messages(self):
        if (not self.user_id) or (not self.chat_uid):
            return
        messages = db.chat.get_messages(self.user_id, self.chat_uid, limit=self.MESSAGES_LIMIT, should_yeild=True)
        for msg in messages:
            steps = msg.get("steps", [])
            for step in steps:
                if step.get("tool_id", False):
                    tool_name = step.get("tool_name", None)
                    tool_content = step.get("tool_result", None)
                    if tool_name and tool_content:
                        yield ToolMessage(name=tool_name, content=tool_content, tool_call_id=step.get("tool_id"))

            prompt = msg.get("prompt", None)
            if prompt:
                user_message = HumanMessage(content=prompt)
            yield user_message
            answer = msg.get("answer", None)
            if answer:
                ai_message = ""
                for part in answer:
                    if part.get("type") == "text":
                        ai_message += part.get("data", "")
                yield AIMessage(content=ai_message)

    def append(self, message):
        if hasattr(self, "messages"):
            self.messages.append(message)

    def build_context(self, prompt):
        if (not self.user_id) or (not self.chat_uid):
            return [HumanMessage(content=prompt)]
        else:
            self.append(HumanMessage(content=prompt))
            context = self.messages
            if self.system_prompt:
                context = [SystemMessage(content=self.system_prompt)] + self.messages
            return context

@lru_cache(maxsize=CONFIG.LRU_CACHE_SIZE)
def get_hrms_context(user_id, chat_uid, system_prompt=None):
    return HrmsContext(user_id, chat_uid, system_prompt)