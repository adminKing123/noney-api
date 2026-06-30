"""
fuse/nodes/ai_generate_text.py
================================
Node handler for plain AI text generation with optional web search tool.
"""

import logging

from langchain.messages import HumanMessage

from fuse.nodes.base import NodeHandler
from fuse.nodes.ai_helpers import (
    create_gemini_model,
    extract_text,
    is_web_search_enabled,
)
from fuse.variable_resolver import resolve_variables

logger = logging.getLogger(__name__)


class AIGenerateTextHandler(NodeHandler):
    def execute(self, config: dict, ctx) -> dict:
        prompt_template = config.get("prompt", "")
        resolved_prompt = resolve_variables(prompt_template, ctx.node_outputs).strip()

        if not resolved_prompt:
            return {"error": "Prompt is empty", "success": False, "text": ""}

        use_web_search = is_web_search_enabled(config)

        try:
            model = create_gemini_model(enable_web_search=use_web_search)
            response = model.invoke([HumanMessage(content=resolved_prompt)])
            text = extract_text(response)
        except Exception as exc:
            logger.exception("[FUSE] ai_generate_text: model invoke failed")
            return {"error": str(exc), "success": False, "text": ""}

        if not text:
            return {
                "error": "AI returned an empty response.",
                "success": False,
                "text": "",
            }

        return {"text": text, "success": True}
