import os
from dotenv import load_dotenv

load_dotenv()

class Hrms:
    HR_CODE = os.getenv("HR_CODE", "aWxlYWRzeW5hcHNlMjAzfFNMQ09OU1RBTlNUTg==")
    API_BASE = os.getenv("HRMS_API_BASE", "https://hrsapi.thesynapses.com")
    DEFAULT_USER_ID = int(os.getenv("HRMS_DEFAULT_USER_ID", "128"))
    DEFAULT_SIGNED_ARRAY = os.getenv("HRMS_DEFAULT_SIGNED_ARRAY", "MTI4fDExMDd8cy5vc2F0d2FsQHRoZXN5bmFwc2VzLmNvbXxTdXBlciBBZG1pbg==")

class Models:
    NONEY_1_0_TWINKLE_20241001 = "noney-1.0-twinkle-20241001"
    NONEY_CODE_GEN_20241001 = "noney-code-gen-20241001"
    NONEY_HRMS_ASSISTANT_20241001 = "noney-hrms-assistant-20241001"
    NONEY_HRMS_ASSISTANT_PRO_20241001 = "noney-hrms-assistant-pro-20241001"
    DEFAULT_MODEL = NONEY_1_0_TWINKLE_20241001

class Uploads:
    UPLOAD_FOLDER = os.getenv("UPLOAD_FOLDER", "uploads")

class CONFIG:
    GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
    FIREBASE_CREDENTIALS = os.getenv("FIREBASE_CREDENTIALS", "")
    DEBUG = os.getenv("DEBUG", "false").lower() == "true"
    LRU_CACHE_SIZE = int(os.getenv("LRU_CACHE_SIZE", "128"))
    GEMINI_MESSAGE_LIMIT = int(os.getenv("GEMINI_MESSAGE_LIMIT", "10"))
    
    GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
    GITHUB_BRANCH_NAME = os.getenv("GITHUB_BRANCH_NAME", "main")
    GITHUB_REPO_NAME = os.getenv("GITHUB_REPO_NAME", "")
    GITHUB_USERNAME = os.getenv("GITHUB_USERNAME", "")

    MODELS = Models()
    UPLOADS = Uploads()
    HRMS = Hrms()

    AI_MAPPINGS = {}

    AI_MAPPINGS[MODELS.NONEY_1_0_TWINKLE_20241001] = {
        "temperature": 0.7,
        "top_p": 1.0,
        "top_k": 40,
        "model_id": "gemini-2.0-flash",
    }

    AI_MAPPINGS[MODELS.NONEY_CODE_GEN_20241001] = {
        "temperature": 0.7,
        "top_p": 1.0,
        "top_k": 40,
        "model_id": "gemini-2.5-flash",
        "system_prompt": '''
You are a helpful and precise AI assistant specialized in code generation and software development tasks. Your primary goal is to assist users by providing accurate, efficient, and well-structured code snippets in response to their programming-related queries.
Guidelines:
1. Always provide code snippets in the requested programming language.
2. if not provided which language, ask the user for clarification.
3. Don't add much explanations unless asked.
4. Ensure code is properly formatted and follows standard conventions.
5. In case of any ambiguity, ask for clarification before proceeding.
6. Be concise and to the point.
7. If the request is outside the scope of programming or code generation, politely inform the user that you are specialized in software engineering tasks only.
8. Always answer in module-level code snippets, avoid writing full applications unless explicitly requested.
9. Strict: Don't answer anything outside Software Engineering Scope, and always maintain professionalism.
'''
    }

    AI_MAPPINGS[MODELS.NONEY_HRMS_ASSISTANT_20241001] = {
        "temperature": 0,
        "top_p": None,
        "top_k": None,
        "model_id": "gemini-2.5-flash",
        "system_prompt": '''
You are an expert HRMS assistant AI specialized in handling Human Resource Management System queries. Your primary goal is to assist users by providing accurate and helpful information related to HRMS functionalities, policies, and procedures.
RULES TO BE FOLLOWED:
- You MUST call `find_user_tool` first for ANY request that needs user_id or signed_array.
- You are NOT allowed to guess or hallucinate user_id or signed_array.
- user_id and signed_array must ONLY come from the response of find_user_tool.
- If find_user_tool returns null or empty, STOP and tell the user you could not find the user.
- If the user is found, reuse the SAME user_id and signed_array for all future tool calls.
- Never ask the user to provide user_id or signed_array manually.
- Check login status before performing login or logout actions.
- If the user is already logged in, do not perform login again; inform the user instead.
- If the user is not logged in, do not perform logout; inform the user instead.
'''
    }

    AI_MAPPINGS[MODELS.NONEY_HRMS_ASSISTANT_PRO_20241001] = {
        "temperature": 0,
        "top_p": None,
        "top_k": None,
        "model_id": "gemini-3-pro-preview",
        "system_prompt": AI_MAPPINGS[MODELS.NONEY_HRMS_ASSISTANT_20241001]["system_prompt"]
    }