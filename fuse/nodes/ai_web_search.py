"""
fuse/nodes/ai_web_search.py
===========================
Node handler for AI-powered web search with required structured output.

Uses Gemini with the google_search tool to gather web-grounded research, then
extracts fields defined in output_schema (same variable shape as
ai_structured_output: {{node_id.result.fieldName}}).
"""

import logging

from langchain.messages import HumanMessage

from fuse.nodes.base import NodeHandler
from fuse.nodes.ai_structured_output import _build_pydantic_model
from fuse.variable_resolver import resolve_variables
from ai.google_text.google_text_ai import GeminiTextAI
from config import CONFIG
from utils.google_citations import get_citations_from_grounding

logger = logging.getLogger(__name__)


def _extract_text(response) -> str:
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


def _extract_sources(response) -> list:
    meta = getattr(response, "response_metadata", {}) or {}
    grounding = meta.get("grounding_metadata") or {}
    chunks = grounding.get("grounding_chunks") or []
    supports = grounding.get("grounding_supports") or []
    if not chunks:
        return []
    try:
        return get_citations_from_grounding(chunks, supports)
    except Exception as exc:
        logger.warning("[FUSE] ai_web_search: failed to build citations — %s", exc)
        return [
            {
                "url": chunk.get("web", {}).get("uri", ""),
                "from": chunk.get("web", {}).get("title", ""),
            }
            for chunk in chunks
            if chunk.get("web", {}).get("uri")
        ]


class AIWebSearchHandler(NodeHandler):
    def execute(self, config: dict, ctx) -> dict:
        prompt_template = config.get("prompt", "")
        resolved_prompt = resolve_variables(prompt_template, ctx.node_outputs).strip()

        output_schema_config = config.get("output_schema") or {}
        schema_fields = output_schema_config.get("fields") or []

        if not resolved_prompt:
            return {"error": "Prompt is empty", "success": False}

        if not schema_fields:
            return {"error": "No output schema defined", "success": False}

        ai = GeminiTextAI(model_name=CONFIG.MODELS.DEFAULT_MODEL)
        DynamicModel = _build_pydantic_model("DynamicWebSearchOutput", schema_fields)

        try:
            response = ai.model.invoke([HumanMessage(content=resolved_prompt)])
        except Exception as exc:
            logger.exception("[FUSE] ai_web_search: model invoke failed")
            return {"error": str(exc), "success": False}

        answer = _extract_text(response)
        if not answer:
            return {"error": "Web search returned an empty answer.", "success": False}

        sources = _extract_sources(response)
        sources_text = ""
        if sources:
            source_lines = [
                f"- {s.get('headline') or s.get('from') or 'Source'}: {s.get('url', '')}"
                for s in sources
                if s.get("url")
            ]
            if source_lines:
                sources_text = "\n\nSources:\n" + "\n".join(source_lines)

        structure_prompt = (
            f"{resolved_prompt}\n\n"
            "Use the following web research to extract the requested structured data.\n\n"
            f"Research answer:\n{answer}"
            f"{sources_text}"
        )

        try:
            structured = ai.with_structured_output(
                DynamicModel,
                method="json_schema",
            ).invoke(structure_prompt)
            result_dict = (
                structured.model_dump()
                if hasattr(structured, "model_dump")
                else structured.dict()
            )
            return {"result": result_dict, "success": True}
        except Exception as exc:
            logger.exception("[FUSE] ai_web_search: structured extraction failed")
            return {"error": str(exc), "success": False}
