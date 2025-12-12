import os
from dotenv import load_dotenv

load_dotenv()

class Models:
    NONEY_1_0_TWINKLE_20241001 = "noney-1.0-twinkle-20241001"
    DEFAULT_MODEL = NONEY_1_0_TWINKLE_20241001

class CONFIG:
    GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
    FIREBASE_CREDENTIALS = os.getenv("FIREBASE_CREDENTIALS", "")
    DEBUG = os.getenv("DEBUG", "false").lower() == "true"
    LRU_CACHE_SIZE = int(os.getenv("LRU_CACHE_SIZE", "128"))
    GEMINI_MESSAGE_LIMIT = int(os.getenv("GEMINI_MESSAGE_LIMIT", "10"))
    MODELS = Models()

    AI_MAPPINGS = {
        "gemini-2.5-flash": {
            "temperature": 0.7,
            "top_p": 1.0,
            "top_k": 40,
            "model_id": MODELS.NONEY_1_0_TWINKLE_20241001,
        },
    }

    AI_MAPPINGS_REVERSED = {
        MODELS.NONEY_1_0_TWINKLE_20241001: "gemini-2.5-flash",
    }