"""
fuse/nodes/ai_structured_output.py
==================================
Node handler for generating structured AI output with optional web search.
"""

from typing import Any, Dict, List, Type, Literal

from pydantic import create_model, Field, BaseModel

from fuse.nodes.base import NodeHandler
from fuse.nodes.ai_helpers import create_gemini_model, is_web_search_enabled
from fuse.variable_resolver import resolve_variables


def _build_pydantic_model(model_name: str, fields: List[Dict[str, Any]]) -> Type[BaseModel]:
    """Recursively build a Pydantic model from the visual schema builder fields."""
    annotations = {}
    for field in fields:
        field_key = field.get("key")
        if not field_key:
            continue

        field_type = field.get("type", "string")
        description = field.get("description", "")

        if field_type == "string":
            enum_str = field.get("enum", "")
            if enum_str:
                enum_values = [v.strip() for v in enum_str.split(",") if v.strip()]
                if enum_values:
                    field_type_hint = Literal[tuple(enum_values)]
                    annotations[field_key] = (field_type_hint, Field(..., description=description))
                    continue
            annotations[field_key] = (str, Field(..., description=description))
        elif field_type == "number":
            annotations[field_key] = (float, Field(..., description=description))
        elif field_type == "boolean":
            annotations[field_key] = (bool, Field(..., description=description))
        elif field_type == "object":
            sub_fields = field.get("fields", [])
            sub_model = _build_pydantic_model(f"{model_name}_{field_key}", sub_fields)
            annotations[field_key] = (sub_model, Field(..., description=description))
        elif field_type == "array":
            items = field.get("items", {})
            item_type = items.get("type", "string")
            if item_type == "string":
                annotations[field_key] = (List[str], Field(..., description=description))
            elif item_type == "number":
                annotations[field_key] = (List[float], Field(..., description=description))
            elif item_type == "boolean":
                annotations[field_key] = (List[bool], Field(..., description=description))
            elif item_type == "object":
                sub_fields = items.get("fields", [])
                sub_model = _build_pydantic_model(f"{model_name}_{field_key}_item", sub_fields)
                annotations[field_key] = (List[sub_model], Field(..., description=description))
            else:
                annotations[field_key] = (List[Any], Field(..., description=description))
        else:
            annotations[field_key] = (Any, Field(..., description=description))

    return create_model(model_name, **annotations)


class AIStructuredOutputHandler(NodeHandler):
    def execute(self, config: dict, ctx) -> dict:
        prompt_template = config.get("prompt", "")
        resolved_prompt = resolve_variables(prompt_template, ctx.node_outputs)

        output_schema_config = config.get("output_schema", {})
        schema_fields = output_schema_config.get("fields", [])

        if not schema_fields:
            return {"error": "No output schema defined", "success": False}

        DynamicModel = _build_pydantic_model("DynamicStructuredOutput", schema_fields)
        use_web_search = is_web_search_enabled(config)

        try:
            model = create_gemini_model(enable_web_search=use_web_search)
            structured = model.with_structured_output(
                DynamicModel,
                method="json_schema",
            ).invoke(resolved_prompt)

            result_dict = (
                structured.model_dump()
                if hasattr(structured, "model_dump")
                else structured.dict()
            )
            return {"result": result_dict, "success": True}
        except Exception as exc:
            return {"error": str(exc), "success": False}
