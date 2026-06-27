"""
fuse/workflow_tools.py
======================
LangChain tools for AI workflow generation.

The model searches a lightweight node index and fetches full config_form details
only for the node types it needs — scalable to hundreds/thousands of nodes.
"""

from __future__ import annotations

import json
from contextvars import ContextVar
from typing import Literal, Optional

from langchain.tools import tool
from pydantic import BaseModel, Field

from fuse.node_catalog import (
    get_node_details,
    search_nodes,
)

# Per-request catalog injected before the tool loop runs.
_catalog_ctx: ContextVar[dict | None] = ContextVar("fuse_workflow_catalog", default=None)
_fetched_types_ctx: ContextVar[set[str]] = ContextVar("fuse_fetched_node_types", default=None)


def set_workflow_tool_context(catalog: dict) -> None:
    _catalog_ctx.set(catalog)
    _fetched_types_ctx.set(set())


def mark_node_types_fetched(node_types: list[str]) -> None:
    _mark_fetched(node_types)


def get_fetched_node_types() -> set[str]:
    return _fetched_types_ctx.get() or set()


def _catalog() -> dict:
    catalog = _catalog_ctx.get()
    if catalog is None:
        raise RuntimeError("Workflow tool context not initialized.")
    return catalog


def _mark_fetched(node_types: list[str]) -> None:
    fetched = _fetched_types_ctx.get()
    if fetched is not None:
        fetched.update(node_types)


class SearchFuseNodesInput(BaseModel):
    query: str = Field(
        description=(
            "Keywords describing the capability you need, e.g. 'webhook POST', "
            "'send email gmail', 'AI summarize', 'schedule daily', 'notification'"
        )
    )
    role: Optional[Literal["starter", "action"]] = Field(
        default=None,
        description="Filter by starter (trigger) or action nodes. Omit to search all.",
    )
    limit: int = Field(default=15, ge=1, le=30, description="Max results to return")


class GetFuseNodeDetailsInput(BaseModel):
    node_types: list[str] = Field(
        description=(
            "List of node_type strings to fetch full configuration requirements for. "
            "Always fetch details for every node you plan to use in the workflow."
        ),
        min_length=1,
        max_length=12,
    )


@tool(args_schema=SearchFuseNodesInput)
def search_fuse_nodes(
    query: str,
    role: Optional[Literal["starter", "action"]] = None,
    limit: int = 15,
) -> str:
    """
    Search available Fuse workflow nodes by keyword.

    Returns a compact list (node_type, label, role, description, section).
    Use this first to discover which nodes exist, then call get_fuse_node_details
    for the node_types you select.
    """
    results = search_nodes(_catalog(), query, role=role, limit=limit)
    return json.dumps({"count": len(results), "nodes": results}, indent=2)


@tool(args_schema=GetFuseNodeDetailsInput)
def get_fuse_node_details(node_types: list[str]) -> str:
    """
    Fetch full configuration requirements for specific node types.

    Returns config_form (fields, types, options, hints), required fields,
    presets, branch_handles, and builder-field formatting rules.
    Call this for every node_type before generating the workflow.
    """
    details, missing = get_node_details(_catalog(), node_types)
    _mark_fetched([d["node_type"] for d in details])
    return json.dumps({"nodes": details, "not_found": missing}, indent=2)


WORKFLOW_TOOLS = [search_fuse_nodes, get_fuse_node_details]

TOOLS_BY_NAME = {t.name: t for t in WORKFLOW_TOOLS}
