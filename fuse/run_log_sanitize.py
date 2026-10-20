"""
fuse/run_log_sanitize.py
========================
Keep fuse_run_logs documents under Firestore's ~1 MiB limit.
"""

from __future__ import annotations

import copy
import json
from typing import Any

# Stay safely under Firestore's 1,048,576-byte document cap.
_MAX_STRING_CHARS = 24_000
_MAX_LIST_ITEMS = 50
_MAX_DICT_KEYS = 80
_MAX_DEPTH = 10

_CREATE_JSON_OUTPUT_KEYS = (
    "success",
    "url",
    "filename",
    "path",
    "size_bytes",
    "content_type",
    "original_name",
)


def create_json_file_log_output(output: dict | None) -> dict | None:
    """Only URL + file metadata — never embed file body in run logs."""
    if not output:
        return output
    return {k: output[k] for k in _CREATE_JSON_OUTPUT_KEYS if k in output}


def _truncate_string(s: str) -> str:
    if len(s) <= _MAX_STRING_CHARS:
        return s
    return (
        s[:_MAX_STRING_CHARS]
        + f"... [truncated — {len(s):,} characters total, omitted from run log]"
    )


def truncate_for_firestore(value: Any, *, depth: int = 0) -> Any:
    """Recursively shrink strings and large collections for Firestore storage."""
    if depth > _MAX_DEPTH:
        return "[truncated: max depth]"

    if value is None or isinstance(value, (bool, int, float)):
        return value

    if isinstance(value, str):
        return _truncate_string(value)

    if isinstance(value, bytes):
        return f"[binary omitted, {len(value):,} bytes]"

    if isinstance(value, dict):
        items = list(value.items())[:_MAX_DICT_KEYS]
        out = {str(k): truncate_for_firestore(v, depth=depth + 1) for k, v in items}
        if len(value) > _MAX_DICT_KEYS:
            out["_truncated_keys"] = len(value) - _MAX_DICT_KEYS
        return out

    if isinstance(value, (list, tuple)):
        sliced = value[:_MAX_LIST_ITEMS]
        out = [truncate_for_firestore(v, depth=depth + 1) for v in sliced]
        if len(value) > _MAX_LIST_ITEMS:
            out.append(f"... [{len(value) - _MAX_LIST_ITEMS} more items omitted]")
        return out

    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        return _truncate_string(str(value))


def redact_config_for_log(node_type: str, config: dict | None) -> dict | None:
    if not config:
        return config
    cfg = copy.deepcopy(config)
    if node_type == "create_json_file":
        raw = cfg.get("json_content")
        if isinstance(raw, str) and raw:
            cfg["json_content"] = (
                f"[omitted from run log — {len(raw):,} characters; "
                "see uploaded file URL in output]"
            )
    return cfg


def prepare_node_log_payload(
    node_type: str,
    *,
    output: dict | None,
    input_snapshot: dict | None,
    config: dict | None,
    variables: dict | None,
    minimal: bool = False,
) -> tuple[dict | None, dict | None, dict | None, dict | None]:
    """
    Returns (output, input, config, variables) safe to persist.

    When ``minimal`` is True, drop input/config/variables entirely.
    """
    if node_type == "create_json_file":
        log_output = create_json_file_log_output(output)
    else:
        log_output = truncate_for_firestore(output) if output is not None else None

    if minimal:
        return log_output, None, None, None

    log_config = redact_config_for_log(node_type, config)
    log_config = truncate_for_firestore(log_config) if log_config is not None else None

    if node_type == "create_json_file":
        log_input: dict | None = {
            "_note": "Upstream node outputs omitted from run log (size limit).",
        }
    else:
        log_input = truncate_for_firestore(input_snapshot) if input_snapshot is not None else None

    log_variables = truncate_for_firestore(variables) if variables is not None else None
    return log_output, log_input, log_config, log_variables


def is_firestore_document_too_large(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return "exceeds the maximum allowed size" in msg or "maximum allowed size" in msg
