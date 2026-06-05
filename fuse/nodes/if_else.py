"""
fuse/nodes/if_else.py
=====================
If/Else branching node handler.

The node evaluates a condition against the current execution context and
returns ``{"result": True|False}``.  The executor uses this to decide which
outgoing edge (``"true"`` or ``"false"`` handle) to follow.

Supported operators (case-insensitive)
---------------------------------------
  Equality   : is, is not
  Comparison : >, <, >=, <=
  Numeric    : is even, is odd
  Presence   : is empty, is not empty
  String     : contains, does not contain,
               starts with, does not start with,
               ends with, does not end with
  Boolean    : is true, is false
"""

import logging
from typing import Any

from .base import NodeHandler
from ..variable_resolver import resolve_single_token

logger = logging.getLogger(__name__)

# Operators that do not require a comparison value
UNARY_OPERATORS: frozenset[str] = frozenset({
    "is even", "is odd",
    "is empty", "is not empty",
    "is true", "is false",
})


# ─── Operator evaluation ───────────────────────────────────────────────────────

def _to_number(value: Any) -> float | None:
    """Attempt numeric coercion; return None if impossible."""
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def apply_operator(value: Any, operator: str, compare: Any) -> bool:
    """
    Apply `operator` to `value` (and `compare` for binary operators).

    Returns a bool result.  Unrecognised operators log a warning and return False.
    """
    op      = (operator or "").strip().lower()
    str_val = str(value) if value is not None else ""
    str_cmp = str(compare) if compare is not None else ""

    # ── Equality ──────────────────────────────────────────────────────────────
    if op == "is":
        return str_val == str_cmp
    if op == "is not":
        return str_val != str_cmp

    # ── Numeric comparison (falls back to lexicographic) ─────────────────────
    if op in (">", "<", ">=", "<="):
        num_val = _to_number(value)
        num_cmp = _to_number(compare)
        if num_val is not None and num_cmp is not None:
            if op == ">":  return num_val > num_cmp
            if op == "<":  return num_val < num_cmp
            if op == ">=": return num_val >= num_cmp
            if op == "<=": return num_val <= num_cmp
        # String fallback
        if op == ">":  return str_val > str_cmp
        if op == "<":  return str_val < str_cmp
        if op == ">=": return str_val >= str_cmp
        if op == "<=": return str_val <= str_cmp

    # ── Numeric parity ────────────────────────────────────────────────────────
    if op == "is even":
        n = _to_number(value)
        return n is not None and int(n) % 2 == 0
    if op == "is odd":
        n = _to_number(value)
        return n is not None and int(n) % 2 != 0

    # ── Presence ──────────────────────────────────────────────────────────────
    if op == "is empty":
        return value is None or value in ("", [], {})
    if op == "is not empty":
        return value is not None and value not in ("", [], {})

    # ── String ────────────────────────────────────────────────────────────────
    if op == "contains":
        return str_cmp in str_val
    if op == "does not contain":
        return str_cmp not in str_val
    if op == "starts with":
        return str_val.startswith(str_cmp)
    if op == "does not start with":
        return not str_val.startswith(str_cmp)
    if op == "ends with":
        return str_val.endswith(str_cmp)
    if op == "does not end with":
        return not str_val.endswith(str_cmp)

    # ── Boolean ───────────────────────────────────────────────────────────────
    _TRUTHY = {True, "true", "True", "1", "yes", "Yes", 1}
    _FALSY  = {False, "false", "False", "0", "no", "No", 0}
    if op == "is true":
        return value in _TRUTHY
    if op == "is false":
        return value in _FALSY

    logger.warning("[FUSE] Unknown operator '%s' — evaluating to False.", operator)
    return False


# ─── Condition evaluation ──────────────────────────────────────────────────────

def evaluate_condition(condition: dict, node_outputs: dict) -> bool:
    """
    Evaluate a condition dict produced by the ConditionBuilder UI component.

    Condition shape::

        {
            "variable": "{{node_id.body.field}}",
            "operator": "is",
            "value":    "active",   # ignored for unary operators
        }

    Returns True (follow the 'true' edge) or False (follow the 'false' edge).
    """
    variable_token = (condition.get("variable") or "").strip()
    operator       = (condition.get("operator") or "").strip()
    compare_value  = condition.get("value", "")

    if not variable_token or not operator:
        logger.warning(
            "[FUSE] Incomplete condition (variable=%r, operator=%r) — defaulting to False.",
            variable_token, operator,
        )
        return False

    value = resolve_single_token(variable_token, node_outputs)
    return apply_operator(value, operator, compare_value)


# ─── Handler ───────────────────────────────────────────────────────────────────

class IfElseHandler(NodeHandler):
    """
    If/Else branching node.

    Output: ``{"result": bool, "condition": dict}``

    The executor reads ``output["result"]`` to decide which branch to follow.
    """

    def execute(self, config: dict, context) -> dict:
        condition     = config.get("condition") or {}
        variable_token = (condition.get("variable") or "").strip()
        operator      = (condition.get("operator") or "").strip()
        compare_value = condition.get("value", "")

        # Resolve the variable to its real runtime value so the log is readable
        from ..variable_resolver import resolve_single_token  # noqa: PLC0415
        resolved_value = resolve_single_token(variable_token, context.node_outputs) if variable_token else None

        result = evaluate_condition(condition, context.node_outputs)

        logger.info(
            "[FUSE] if_else evaluated — workflow=%s run=%s",
            context.workflow_id, context.run_id,
        )
        logger.info(
            "[FUSE]   variable  = %s",
            variable_token,
        )
        logger.info(
            "[FUSE]   value     = %r  (resolved from token)",
            resolved_value,
        )
        logger.info(
            "[FUSE]   operator  = %s",
            operator,
        )
        logger.info(
            "[FUSE]   compare   = %r",
            compare_value,
        )
        logger.info(
            "[FUSE]   result    = %s  → following '%s' branch",
            result, "true" if result else "false",
        )
        return {"result": result, "condition": condition}
