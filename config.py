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