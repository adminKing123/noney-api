"""
fuse/nodes/ai_helpers.py
========================
Shared helpers for Fuse AI node handlers.
"""

from langchain_google_genai import ChatGoogleGenerativeAI

from config import CONFIG


def is_web_search_enabled(config: dict) -> bool:
    """Return True when the node config has web search tool enabled."""
    raw = config.get("web_search")
    if isinstance(raw, bool):
        return raw
    if isinstance(raw, str):
        return raw.lower() in ("true", "1", "yes", "on")
    return False


def create_gemini_model(*, enable_web_search: bool = False) -> ChatGoogleGenerativeAI:
    """Build a Gemini chat model, optionally with the google_search tool."""
    details = CONFIG.AI_MAPPINGS.get(CONFIG.MODELS.DEFAULT_MODEL, {})
    model = ChatGoogleGenerativeAI(
        model=details.get("model_id"),
        temperature=details.get("temperature", 0.7),
        top_p=details.get("top_p", 1.0),
        top_k=details.get("top_k", 40),
    )
    if enable_web_search:
        model = model.bind_tools([{"google_search": {}}])
    return model


def extract_text(response) -> str:
    content = getattr(response, "content", "")
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict) and "text" in block:
                parts.append(block["text"])
            elif isinstance(block, str):
                parts.append(block)
        return "".join(parts).strip()
    return str(content or "").strip()
