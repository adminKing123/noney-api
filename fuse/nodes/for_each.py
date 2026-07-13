"""
fuse/nodes/for_each.py
======================
For Each loop node handler.

This handler resolves the configured array variable and stores it in the
execution output so the executor can iterate over it.  The actual looping
is handled by a dedicated code path in ``executor.py`` — this handler is
responsible only for resolving and validating the input array.

The executor injects ``current_item`` and ``current_index`` into this
node's output before each body iteration so downstream body nodes can
reference them via ``{{node_id.current_item}}`` and
``{{node_id.current_index}}``.

Output
------
{
    "items":         list,   -- resolved array
    "count":         int,    -- number of items
    "current_item":  None,   -- populated per-iteration by the executor
    "current_index": -1,     -- populated per-iteration by the executor
}
"""

import logging

from .base import NodeHandler
from ..variable_resolver import resolve_single_token

logger = logging.getLogger(__name__)


class ForEachHandler(NodeHandler):
    """
    For Each loop — iterates the body branch once per element of an array.

    Config keys
    -----------
    array_variable : str   A ``{{token}}`` that must resolve to a Python list.
    """

    def execute(self, config: dict, context) -> dict:
        token = (config.get("array_variable") or "").strip()

        if not token:
            logger.warning(
                "[FUSE] for_each — no array_variable configured. "
                "(workflow=%s run=%s)",
                context.workflow_id, context.run_id,
            )
            return {"items": [], "count": 0, "current_item": None, "current_index": -1}

        value = resolve_single_token(token, context.node_outputs)

        if not isinstance(value, list):
            logger.warning(
                "[FUSE] for_each — '%s' resolved to type %s (expected list). "
                "Wrapping in a single-element list. (workflow=%s run=%s)",
                token, type(value).__name__,
                context.workflow_id, context.run_id,
            )
            value = [] if value is None else [value]

        logger.info(
            "[FUSE] for_each — will iterate over %d item(s). (workflow=%s run=%s)",
            len(value), context.workflow_id, context.run_id,
        )

        return {
            "items":         value,
            "count":         len(value),
            "current_item":  None,
            "current_index": -1,
        }
