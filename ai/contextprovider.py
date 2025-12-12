from config import CONFIG
from .google_text_context import get_google_text_context

class ContextProvider:
    @staticmethod
    def get(model_id, user_id, chat_uid):
        if model_id == CONFIG.MODELS.NONEY_1_0_TWINKLE_20241001:
            return get_google_text_context(user_id, chat_uid)
        
        # for now returning google text context as default
        return get_google_text_context(user_id, chat_uid)
        
