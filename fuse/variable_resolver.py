"""
fuse/variable_resolver.py
=========================
Resolves {{node_id.body.field.path}} variable tokens against an execution
context's node_outputs dictionary.

Token format
------------
{{<node_id>.<path>}}

Where <path> is a dot-separated sequence of key names.  Array notation is
supported:  "items[]"  returns the full list;  "items[].userId" maps the
"userId" key over each list element and returns a list of values.

Public API
----------
resolve_variables(template, node_outputs)         -> str
resolve_single_token(token_str, node_outputs)     -> Any
"""

import re
import logging
from typing import Any

logger = logging.getLogger(__name__)


# Matches {{anything}} — the inner content is captured in group 1.
_TOKEN_RE = re.compile(r"\{\{([^}]+)\}\}")


# ─── Path traversal ────────────────────────────────────────────────────────────

def _resolve_path(data: Any, path_str: str) -> Any:
    """
    Traverse `data` following the dot-separated `path_str`.

    Handles array notation:
      "items[]"         — return the list at key "items"
      "items[].userId"  — map "userId" over each list element
    """
    if not path_str:
        return data

    parts = path_str.split(".")
    current: Any = data

    for part in parts:
        if current is None:
            return None

        # Strip array suffix if present
        is_array_accessor = part.endswith("[]")
        key = part[:-2] if is_array_accessor else part

        if isinstance(current, dict):
            current = current.get(key)
        elif isinstance(current, list):
            # Map the key over each list element
            current = [
                item.get(key) if isinstance(item, dict) else None
                for item in current
            ]
        else:
            return None

    return current


# ─── Public helpers ────────────────────────────────────────────────────────────

def resolve_single_token(token_str: str, node_outputs: dict) -> Any:
    """
    Resolve a single token string (e.g. "{{node_abc.body.status}}") to its
    runtime value.

    Returns None if the token is malformed or the path does not exist.
    """
    token_str = token_str.strip()
    match = _TOKEN_RE.fullmatch(token_str)
    if not match:
        return None

    inner = match.group(1).strip()
    # Split only on the first dot: node_id is everything before it
    dot_pos = inner.find(".")
    if dot_pos == -1:
        # No path — return the entire node output
        return node_outputs.get(inner)

    node_id  = inner[:dot_pos]
    path_str = inner[dot_pos + 1:]
    node_data = node_outputs.get(node_id, {})
    value = _resolve_path(node_data, path_str)

    # Legacy http_request tokens used flat {{node_id.field}} paths before
    # response data was kept only under "body". Fall back to body.* when needed.
    if value is None:
        body = node_data.get("body")
        if isinstance(body, dict) and path_str:
            reserved = frozenset({"status_code", "success", "body", "error"})
            first_seg = path_str.split(".", 1)[0]
            if first_seg not in reserved:
                value = _resolve_path(body, path_str)

    return value


def resolve_variables(template: str, node_outputs: dict) -> str:
    """
    Replace every {{token}} in `template` with its resolved string value.

    Unresolved tokens (path not found) are left in place unchanged so the
    user can debug them.  Dict / list values are JSON-serialised.
    """
    if not isinstance(template, str):
        return str(template) if template is not None else ""

    def _replacer(match: re.Match) -> str:
        token_inner = match.group(1).strip()
        dot_pos = token_inner.find(".")
        if dot_pos == -1:
            value = node_outputs.get(token_inner)
        else:
            node_id  = token_inner[:dot_pos]
            path_str = token_inner[dot_pos + 1:]
            node_data = node_outputs.get(node_id, {})
            value = _resolve_path(node_data, path_str)

            if value is None:
                body = node_data.get("body")
                if isinstance(body, dict) and path_str:
                    reserved = frozenset({"status_code", "success", "body", "error"})
                    first_seg = path_str.split(".", 1)[0]
                    if first_seg not in reserved:
                        value = _resolve_path(body, path_str)

        if value is None:
            logger.debug(
                "[FUSE] Variable token '{{%s}}' could not be resolved — "
                "node '%s' not in outputs or path '%s' returned null. "
                "Available node ids: %s",
                token_inner, node_id, path_str, list(node_outputs.keys()),
            )
            return match.group(0)  # Leave unresolved tokens intact

        if isinstance(value, (dict, list)):
            import json
            return json.dumps(value)

        return str(value)

    return _TOKEN_RE.sub(_replacer, template)
