import os
from dotenv import load_dotenv

load_dotenv()

CONFIG = {
    "GOOGLE_API_KEY": os.getenv("GOOGLE_API_KEY", ""),
    "FIREBASE_CREDENTIALS": os.getenv("FIREBASE_CREDENTIALS"),
}