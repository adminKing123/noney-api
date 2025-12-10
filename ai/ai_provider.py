from ai.google_text_ai import GeminiTextAI

class Models:
    NONEY_1_0_TWINKLE_20241001 = "noney-1.0-twinkle-20241001"
    DEFAULT_MODEL = NONEY_1_0_TWINKLE_20241001


class AIProvider(Models):
    def get(self, model_name: str):
        if (model_name == self.NONEY_1_0_TWINKLE_20241001):
            return GeminiTextAI(model_name="gemini-2.5-flash")
            