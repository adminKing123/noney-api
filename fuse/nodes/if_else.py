"""
fuse/nodes/if_else.py
=====================
If/Else branching node handler.

The node evaluates a condition (or a group of AND/OR conditions) against the
current execution context and returns ``{"result": True|False}``.  The executor
uses this to decide which outgoing edge (``"true"`` or ``"false"`` handle) to
follow.

Condition formats
-----------------
Single (legacy)::

    {
        "variable": "{{node_id.field}}",
        "operator": "is",
        "value":    "active",
    }

Compound (new — produced by the ConditionBuilderField UI)::

    {
        "combinator": "and" | "or",
        "conditions": [
            {"variable": "{{node_id.field}}",  "operator": "is",  "value": "active"},
            {"variable": "{{node_id.field2}}", "operator": ">",   "value": "10"},
        ],
    }

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

def _evaluate_single(condition: dict, node_outputs: dict) -> bool:
    """
    Evaluate one atomic condition dict.

    Shape::

        {
            "variable": "{{node_id.body.field}}",
            "operator": "is",
            "value":    "active",   # ignored for unary operators
        }

    Returns True or False.
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


def evaluate_condition(condition: dict, node_outputs: dict) -> bool:
    """
    Evaluate a condition value produced by the ConditionBuilderField UI.

    Accepts both formats:

    * **Compound** (new): ``{ "combinator": "and"|"or", "conditions": [...] }``
    * **Single** (legacy): ``{ "variable": "...", "operator": "...", "value": "..." }``

    Returns True (follow the ``'true'`` edge) or False (follow the ``'false'`` edge).
    """
    # ── Compound format ──────────────────────────────────────────────────────
    if "conditions" in condition:
        conditions  = condition.get("conditions") or []
        combinator  = (condition.get("combinator") or "and").strip().lower()

        if not conditions:
            logger.warning("[FUSE] Compound condition has no sub-conditions — defaulting to False.")
            return False

        results = [_evaluate_single(c, node_outputs) for c in conditions]

        if combinator == "or":
            return any(results)
        # Default to AND for unknown combinators as well
        return all(results)

    # ── Legacy single format ─────────────────────────────────────────────────
    return _evaluate_single(condition, node_outputs)


# ─── Handler ───────────────────────────────────────────────────────────────────

class IfElseHandler(NodeHandler):
    """
    If/Else branching node.

    Supports both single conditions and compound AND/OR condition groups.

    Output: ``{"result": bool, "condition": dict}``

    The executor reads ``output["result"]`` to decide which branch to follow.
    """

    def execute(self, config: dict, context) -> dict:
        condition  = config.get("condition") or {}
        is_compound = "conditions" in condition

        result = evaluate_condition(condition, context.node_outputs)

        logger.info(
            "[FUSE] if_else evaluated — workflow=%s run=%s  result=%s → '%s' branch",
            context.workflow_id, context.run_id, result, "true" if result else "false",
        )

        if is_compound:
            combinator  = (condition.get("combinator") or "and").upper()
            sub_conditions = condition.get("conditions") or []
            logger.info("[FUSE]   combinator = %s  (%d condition(s))", combinator, len(sub_conditions))

            for idx, cond in enumerate(sub_conditions, start=1):
                variable_token = (cond.get("variable") or "").strip()
                operator       = (cond.get("operator") or "").strip()
                compare_value  = cond.get("value", "")
                resolved_value = (
                    resolve_single_token(variable_token, context.node_outputs)
                    if variable_token else None
                )
                sub_result = _evaluate_single(cond, context.node_outputs)
                logger.info(
                    "[FUSE]   [%d/%d] %s %s %r  → resolved=%r  sub_result=%s",
                    idx, len(sub_conditions),
                    variable_token, operator, compare_value,
                    resolved_value, sub_result,
                )
        else:
            # Legacy single-condition logging
            variable_token = (condition.get("variable") or "").strip()
            operator       = (condition.get("operator") or "").strip()
            compare_value  = condition.get("value", "")
            resolved_value = (
                resolve_single_token(variable_token, context.node_outputs)
                if variable_token else None
            )
            logger.info("[FUSE]   variable  = %s", variable_token)
            logger.info("[FUSE]   value     = %r  (resolved from token)", resolved_value)
            logger.info("[FUSE]   operator  = %s", operator)
            logger.info("[FUSE]   compare   = %r", compare_value)

        return {"result": result, "condition": condition}
