"""
fuse/node_registry.py
=====================
n8n-style node catalog discovery: co-located ``NODE_DEFINITION`` on handler
modules, merged with bundled definitions in ``node_definitions.py``.

Saved workflows, API routes, compiler, and AI tools keep using ``node_type``
strings and the same JSON shapes — only where definitions live changes over time.
"""

from __future__ import annotations

import importlib
import logging
import pkgutil
from typing import Literal

log = logging.getLogger(__name__)

NodeRole = Literal["starter", "action"]

_SKIP_MODULES = frozenset({"base", "ai_helpers", "__init__"})


def _discover_colocated_definitions() -> dict[str, tuple[dict, NodeRole]]:
    """Load NODE_DEFINITION (+ NODE_ROLE) from fuse.nodes.* modules."""
    import fuse.nodes as nodes_pkg

    by_type: dict[str, tuple[dict, NodeRole]] = {}
    for _importer, modname, _ispkg in pkgutil.iter_modules(nodes_pkg.__path__):
        if modname.startswith("_") or modname in _SKIP_MODULES:
            continue
        mod = importlib.import_module(f"fuse.nodes.{modname}")
        definition = getattr(mod, "NODE_DEFINITION", None)
        if not definition:
            continue
        node_type = definition.get("type")
        if not node_type:
            log.warning("fuse.nodes.%s: NODE_DEFINITION missing 'type'", modname)
            continue
        role = getattr(mod, "NODE_ROLE", "action")
        if role not in ("starter", "action"):
            log.warning(
                "fuse.nodes.%s: invalid NODE_ROLE %r; defaulting to 'action'",
                modname,
                role,
            )
            role = "action"
        if node_type in by_type:
            log.warning("Duplicate NODE_DEFINITION for type %r (module %s)", node_type, modname)
        by_type[node_type] = (definition, role)
    return by_type


def build_node_catalog(
    bundled_starters: list[dict],
    bundled_actions: list[dict],
) -> tuple[list[dict], list[dict]]:
    """
    Merge bundled lists with co-located module definitions.

    Co-located definitions win for the same ``type`` (bundled entry is dropped).
    """
    discovered = _discover_colocated_definitions()
    overridden = set(discovered.keys())

    starters: list[dict] = []
    actions: list[dict] = []

    for node in bundled_starters:
        node_type = node.get("type")
        if node_type in overridden:
            continue
        starters.append(node)

    for node in bundled_actions:
        node_type = node.get("type")
        if node_type in overridden:
            continue
        actions.append(node)

    for node_type, (definition, role) in sorted(discovered.items(), key=lambda x: x[0]):
        if role == "starter":
            starters.append(definition)
        else:
            actions.append(definition)

    _validate_handlers_vs_catalog(starters + actions)
    return starters, actions


def _validate_handlers_vs_catalog(all_definitions: list[dict]) -> None:
    """Log mismatches between HANDLERS and catalog (non-fatal)."""
    try:
        from fuse.nodes import HANDLERS
    except ImportError:
        return

    catalog_types = {n.get("type") for n in all_definitions if n.get("type")}
    handler_types = set(HANDLERS.keys())

    for node_type in sorted(catalog_types - handler_types):
        log.warning("Node catalog entry %r has no HANDLERS entry", node_type)
    for node_type in sorted(handler_types - catalog_types):
        log.warning("HANDLERS entry %r has no catalog definition", node_type)
