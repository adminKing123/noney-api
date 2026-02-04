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
            content_parts = []
            if prompt:
                content_parts.append({
                    "type": "text",
                    "text": prompt
                })
            for file in msg.get("files", []):
                file_uri = file.get("genai_file", {}).get("uri", None)
                if file_uri:
                    content_parts.append({
                        "type": "media",
                        "file_uri": file_uri,
                        "mime_type": file.get("genai_file", {}).get("mime_type", None),
                    })
            user_message = HumanMessage(content=content_parts)
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

    def build_context(self, prompt, files=[]):
        content_parts=[]

        if prompt:
            content_parts.append({
                "type": "text",
                "text": prompt
            })
        
        for file in files:
            file_uri = file.get("genai_file", {}).get("uri", None)
            if file_uri:
                content_parts.append({
                    "type": "media",
                    "file_uri": file_uri,
                    "mime_type": file.get("genai_file", {}).get("mime_type", None),
                })

        if (not self.user_id) or (not self.chat_id):
            return [HumanMessage(content=content_parts)]
        else:
            self.append(HumanMessage(content=content_parts))
            context = self.messages
            if self.system_prompt:
                context = [SystemMessage(content=self.system_prompt)] + self.messages
            return context

@lru_cache(maxsize=CONFIG.LRU_CACHE_SIZE)
def get_google_text_context(user_id, chat_id, system_prompt=None):
    return GoogleTextContext(user_id, chat_id, system_prompt)