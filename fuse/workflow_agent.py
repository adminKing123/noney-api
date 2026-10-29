"""
fuse/workflow_agent.py
======================
Tool-calling discovery phase for AI workflow generation.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from langchain.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from fuse.workflow_tools import (
    TOOLS_BY_NAME,
    WORKFLOW_TOOLS,
    get_fetched_node_types,
    mark_node_types_fetched,
    set_workflow_tool_context,
)

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 8

DISCOVERY_SYSTEM_PROMPT = """You are a Fuse Workflow Research Assistant.

Your job is to find the right workflow nodes BEFORE any workflow is built.

You MUST use the provided tools:
1. search_fuse_nodes — search by keywords (run multiple searches if needed: starter/trigger, then actions).
2. get_fuse_node_details — fetch full config requirements for EVERY node_type you plan to use.

Rules:
- Every workflow needs exactly ONE starter (role=starter). Search for starters separately if needed.
- Never invent node types — only use types returned by search_fuse_nodes.
- Always call get_fuse_node_details for each node_type before finishing research.
- Do not generate the workflow JSON yet — only research and summarize your node choices.
"""

GENERATION_INSTRUCTION = """You have finished researching nodes. Now produce the complete workflow plan.

Use ONLY node types you fetched via get_fuse_node_details.
Follow every config_form field, required_fields, value_format, and rules from those details.

Workflow rules:
- Exactly one starter node; all action nodes reachable from it.
- Use logical refs (starter, step_1, ai_1, …) — not UUIDs.
- Variables: {{node_ref.field}} or {{node_ref.body.fieldName}} for webhook body fields.
- body_builder / json_value_builder: set rootType (object|array|string|number|boolean; default object) and preserve exact field types — never default all to string.
- For branch_handles nodes, use source_handle on outgoing edges.
- Fill all required_fields with realistic values from the user's goal.
"""


def run_discovery_phase(model: Any, user_prompt: str, catalog: dict) -> list:
    """
    Run the tool loop so the model searches nodes and fetches details.

    Returns the full message list (including tool results) for the generation phase.
    """
    set_workflow_tool_context(catalog)
    bound = model.bind_tools(WORKFLOW_TOOLS)

    messages = [
        SystemMessage(content=DISCOVERY_SYSTEM_PROMPT),
        HumanMessage(content=user_prompt),
    ]

    for round_num in range(MAX_TOOL_ROUNDS):
        response = bound.invoke(messages)
        messages.append(response)

        tool_calls = getattr(response, "tool_calls", None) or []
        if not tool_calls:
            logger.debug("[FUSE AI] Discovery finished after %d rounds (no tool calls)", round_num + 1)
            break

        for tc in tool_calls:
            name = tc.get("name", "")
            args = tc.get("args") or {}
            tool_id = tc.get("id") or f"call_{round_num}_{name}"

            tool = TOOLS_BY_NAME.get(name)
            if tool is None:
                result = json.dumps({"error": f"Unknown tool: {name}"})
            else:
                try:
                    result = tool.invoke(args)
                except Exception as exc:
                    result = json.dumps({"error": str(exc)})

            messages.append(
                ToolMessage(content=result, tool_call_id=tool_id, name=name)
            )

    fetched = get_fetched_node_types()
    if not fetched:
        # Force-fetch all starters so generation always has starter specs
        from fuse.node_catalog import get_node_details
        starter_types = [n["type"] for n in catalog.get("starters") or []]
        if starter_types:
            details, _ = get_node_details(catalog, starter_types[:3])
            mark_node_types_fetched([d["node_type"] for d in details])
            messages.append(
                HumanMessage(
                    content=(
                        "Starter node reference (use one of these as the workflow trigger):\n"
                        f"```json\n{json.dumps(details, indent=2)}\n```"
                    )
                )
            )

    return messages


def build_generation_messages(discovery_messages: list, extra: str = "") -> list:
    """Append the final generation instruction."""
    out = list(discovery_messages)
    text = GENERATION_INSTRUCTION
    if extra:
        text += f"\n\n{extra}"
    out.append(HumanMessage(content=text))
    return out
