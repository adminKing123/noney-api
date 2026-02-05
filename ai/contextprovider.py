from functools import lru_cache
from langchain.messages import HumanMessage, AIMessage, SystemMessage
from config import CONFIG
from db import db


class ContextProvider:
    """Unified context provider for all Gemini-based models"""
    
    MESSAGES_LIMIT = CONFIG.GEMINI_MESSAGE_LIMIT

    def __init__(self, model_name, user_id, chat_id, system_prompt=None):
        self.model_name = model_name
        self.user_id = user_id
        self.chat_id = chat_id
        self.system_prompt = system_prompt
        self.messages = list(self._get_messages())

    def _get_messages(self):
        """Retrieve messages from database"""
        if (not self.user_id) or (not self.chat_id):
            return
        
        messages = db.chat.get_messages(
            self.user_id, 
            self.chat_id, 
            limit=self.MESSAGES_LIMIT, 
            should_yeild=True
        )
        
        for msg in messages:
            # Process user message
            user_message = self._process_user_message(msg)
            if user_message:
                yield user_message
            
            # Process AI response
            ai_message = self._process_ai_message(msg)
            if ai_message:
                yield ai_message

    def _process_user_message(self, msg):
        """Process user message based on model type"""
        prompt = msg.get("prompt", None)
        
        # For models that support files (text and image models)
        if self._supports_files():
            files = msg.get("files", [])
            content_parts = self._build_content_parts(prompt, files)
            return HumanMessage(content=content_parts)
        
        # For simple text-only models (HRMS)
        if prompt:
            return HumanMessage(content=prompt)
        return None

    def _process_ai_message(self, msg):
        """Process AI response message"""
        answer = msg.get("answer", None)
        if answer:
            ai_message = ""
            for part in answer:
                if part.get("type") == "text":
                    ai_message += part.get("data", "")
            return AIMessage(content=ai_message)
        return None

    def _build_content_parts(self, prompt, files):
        """Build content parts from prompt and files"""
        content_parts = []
        if prompt:
            content_parts.append({
                "type": "text",
                "text": prompt
            })
        for file in files:
            file_uri = file.get("genai_file", {}).get("uri", None)
            if file_uri:
                content_parts.append({
                    "type": "file",
                    "file_id": file_uri,
                    "mime_type": file.get("genai_file", {}).get("mime_type", None),
                })
        return content_parts

    def _supports_files(self):
        """Check if model supports file attachments"""
        return self.model_name in [
            CONFIG.MODELS.NONEY_1_0_TWINKLE_20241001,
            CONFIG.MODELS.NONEY_2_0_TWINKLE_20241001,
            CONFIG.MODELS.NONEY_CODE_GEN_20241001,
            CONFIG.MODELS.NONEY_CODE_GEN_PRO_20241001,
            CONFIG.MODELS.NONEY_IMAGE_GEN_20241001
        ]

    def append(self, message):
        """Append a message to the conversation"""
        if hasattr(self, "messages"):
            self.messages.append(message)

    def build_context(self, prompt, files=[]):
        """Build context for the AI model"""
        # Build new message based on model type
        if self._supports_files():
            content_parts = self._build_content_parts(prompt, files)
            new_message = HumanMessage(content=content_parts)
        else:
            new_message = HumanMessage(content=prompt)
        
        # Return context with or without history
        if (not self.user_id) or (not self.chat_id):
            return [new_message]
        else:
            self.append(new_message)
            context = self.messages
            if self.system_prompt:
                context = [SystemMessage(content=self.system_prompt)] + self.messages
            return context

    @staticmethod
    @lru_cache(maxsize=CONFIG.LRU_CACHE_SIZE)
    def get(model_name, user_id, chat_id, system_prompt=None):
        """Factory method to get context provider instance"""
        return ContextProvider(model_name, user_id, chat_id, system_prompt)

        
        
