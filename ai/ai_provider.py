from .google_text.google_text_ai import GeminiTextAI
from .hrms_preview_text.hrms_preview_ai import HrmsPreviewAI
from config import CONFIG

class AIProvider:
    def get(self, model_name):
        if (model_name == CONFIG.MODELS.NONEY_1_0_TWINKLE_20241001):
            return GeminiTextAI(model_name=CONFIG.MODELS.NONEY_1_0_TWINKLE_20241001)
        if (model_name == CONFIG.MODELS.NONEY_CODE_GEN_20241001):
            return GeminiTextAI(model_name=CONFIG.MODELS.NONEY_CODE_GEN_20241001)
        if (model_name == CONFIG.MODELS.NONEY_HRMS_ASSISTANT_20241001):
            return HrmsPreviewAI(model_name=CONFIG.MODELS.NONEY_HRMS_ASSISTANT_20241001)