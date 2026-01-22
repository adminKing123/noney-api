from .google_text.google_text_ai import GeminiTextAI
from .hrms_preview_text.hrms_preview_ai import HrmsPreviewAI
from .google_image.google_image_ai import GeminiImageAI
from config import CONFIG

class AIProvider:
    def get(self, model_name):
        if (model_name == CONFIG.MODELS.NONEY_1_0_TWINKLE_20241001):
            return GeminiTextAI(model_name=CONFIG.MODELS.NONEY_1_0_TWINKLE_20241001)
        if (model_name == CONFIG.MODELS.NONEY_2_0_TWINKLE_20241001):
            return GeminiTextAI(model_name=CONFIG.MODELS.NONEY_2_0_TWINKLE_20241001)
        if (model_name == CONFIG.MODELS.NONEY_CODE_GEN_20241001):
            return GeminiTextAI(model_name=CONFIG.MODELS.NONEY_CODE_GEN_20241001)
        if (model_name == CONFIG.MODELS.NONEY_CODE_GEN_PRO_20241001):
            return GeminiTextAI(model_name=CONFIG.MODELS.NONEY_CODE_GEN_PRO_20241001)
        if (model_name == CONFIG.MODELS.NONEY_HRMS_ASSISTANT_20241001):
            return HrmsPreviewAI(model_name=CONFIG.MODELS.NONEY_HRMS_ASSISTANT_20241001)
        if (model_name == CONFIG.MODELS.NONEY_HRMS_ASSISTANT_PRO_20241001):
            return HrmsPreviewAI(model_name=CONFIG.MODELS.NONEY_HRMS_ASSISTANT_PRO_20241001)
        if (model_name == CONFIG.MODELS.NONEY_IMAGE_GEN_20241001):
            return GeminiImageAI(model_name=CONFIG.MODELS.NONEY_IMAGE_GEN_20241001)