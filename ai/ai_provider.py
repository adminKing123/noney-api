from ai.google_text_ai import GeminiTextAI
from config import CONFIG

class AIProvider:
    def get(self, model_name):
        if (model_name == CONFIG.MODELS.NONEY_1_0_TWINKLE_20241001):
            return GeminiTextAI(model_name=CONFIG.AI_MAPPINGS_REVERSED[model_name])
        if (model_name == CONFIG.MODELS.NONEY_CODE_GEN_20241001):
            return GeminiTextAI(model_name=CONFIG.AI_MAPPINGS_REVERSED[model_name])