from db import db
from functools import lru_cache
from langchain.messages import HumanMessage, AIMessage, SystemMessage
from config import CONFIG

class GoogleTextContext:
    MESSAGES_LIMIT = CONFIG.GEMINI_MESSAGE_LIMIT

    def __init__(self, user_id, chat_id, system_prompt=None):
        self.user_id = user_id
        self.chat_id = chat_id
        self.system_prompt = system_prompt
        self.messages = list(self._get_messages())

    def _get_messages(self):
        if (not self.user_id) or (not self.chat_id):
            return
        messages = db.chat.get_messages(self.user_id, self.chat_id, limit=self.MESSAGES_LIMIT, should_yeild=True)
        for msg in messages:
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
        if (not self.user_id) or (not self.chat_id):
            return [HumanMessage(content=prompt)]
        else:
            self.append(HumanMessage(content=prompt))
            context = self.messages
            if self.system_prompt:
                context = [SystemMessage(content=self.system_prompt)] + self.messages
            return context

@lru_cache(maxsize=CONFIG.LRU_CACHE_SIZE)
def get_google_text_context(user_id, chat_id, system_prompt=None):
    return GoogleTextContext(user_id, chat_id, system_prompt)