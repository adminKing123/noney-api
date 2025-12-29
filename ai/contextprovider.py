from config import CONFIG
from .google_text.google_text_context import get_google_text_context
from .hrms_preview_text.hrms_context import get_hrms_context

class ContextProvider:
    @staticmethod
    def get(model_name, user_id, chat_uid, system_prompt=None):
        if model_name == CONFIG.MODELS.NONEY_1_0_TWINKLE_20241001:
            return get_google_text_context(user_id, chat_uid, system_prompt)
        if model_name == CONFIG.MODELS.NONEY_CODE_GEN_20241001:
            return get_google_text_context(user_id, chat_uid, system_prompt)
        if model_name == CONFIG.MODELS.NONEY_HRMS_ASSISTANT_20241001:
            return get_hrms_context(user_id, chat_uid, system_prompt)
        if model_name == CONFIG.MODELS.NONEY_HRMS_ASSISTANT_PRO_20241001:
            return get_hrms_context(user_id, chat_uid, system_prompt)
        return get_google_text_context(user_id, chat_uid, system_prompt)
        
        
