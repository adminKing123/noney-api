"""
fuse/nodes/http_request.py
==========================
HTTP Request action node handler.

Makes an outbound HTTP request and exposes the response fields as variables
for downstream nodes via the variable resolver.

Config schema (driven by the form definition in routes/fuse.py)
---------------------------------------------------------------
{
    "method":          str,                        # GET | POST | PUT | PATCH | DELETE
    "url":             str,                        # variable_text — endpoint to call
    "query_params":    JsonValueBuilderEnvelope,   # json_value_builder (flat after resolve)
    "headers":         JsonValueBuilderEnvelope,   # json_value_builder (flat after resolve)
    "payload":         JsonValueBuilderEnvelope,   # json_value_builder (full nested JSON)
    "response_schema": {"mode": "visual", "fields": [...]},  # body_builder
    "timeout":         str | int,                  # seconds, default 30
}

JsonValueBuilderEnvelope:
    { "mode": "visual", "fields": [{ "key", "type", "value", "fields?" }] }

Output (stored in context.node_outputs[node_id])
-------------------------------------------------
{
    "status_code": int,   — HTTP response status code
    "success":     bool,  — True when status is 2xx
    "body":        Any,   — parsed JSON body (dict/list) or raw text string
    "error":       str,   — only present when the request fails entirely
}

Variable resolution
-------------------
    {{node_id.status_code}}
    {{node_id.success}}
    {{node_id.body}}
    {{node_id.body.<response_schema_field>}}
"""

import json as _json
import logging
from typing import Any

import httpx

from .base import NodeHandler
from ..variable_resolver import resolve_variables

logger = logging.getLogger(__name__)

# Maximum response body we will attempt to parse (5 MB)
_MAX_RESPONSE_BYTES = 5 * 1024 * 1024

# Default request timeout in seconds
_DEFAULT_TIMEOUT = 30.0


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _resolve_element_value(element: dict, node_outputs: dict) -> Any:
    ftype = element.get("type", "string")
    if ftype == "object":
        return _build_json_from_value_fields(element.get("fields", []), node_outputs)
    elif ftype == "array":
        return [_resolve_element_value(e, node_outputs) for e in element.get("elements", [])]
    else:
        raw = element.get("value") or ""
        resolved = resolve_variables(raw, node_outputs)
        if ftype == "number":
            try:
                return float(resolved) if "." in resolved else int(resolved)
            except (ValueError, TypeError):
                return resolved
        elif ftype == "boolean":
            return resolved.lower() not in ("false", "0", "no", "")
        return resolved

def _build_json_from_value_fields(fields: list, node_outputs: dict) -> dict:
    """
    Recursively convert JsonValueBuilderField data into a real Python dict with
    all ``{{variable}}`` tokens resolved in every value.
    """
    result: dict = {}
    for field in (fields or []):
        key = (field.get("key") or "").strip()
        if not key:
            continue
        ftype = field.get("type", "string")

        if ftype == "object":
            result[key] = _build_json_from_value_fields(
                field.get("fields", []), node_outputs
            )
        elif ftype == "array":
            # If visual elements exist, use them, otherwise fallback to parsing string
            if "elements" in field:
                result[key] = [_resolve_element_value(e, node_outputs) for e in field["elements"]]
            else:
                raw = field.get("value") or ""
                resolved = resolve_variables(raw, node_outputs)
                try:
                    parsed = _json.loads(resolved)
                    result[key] = parsed if isinstance(parsed, list) else [parsed]
                except Exception:
                    result[key] = [resolved] if resolved else []
        else:
            raw      = field.get("value") or ""
            resolved = resolve_variables(raw, node_outputs)

            if ftype == "number":
                try:
                    result[key] = (
                        float(resolved) if "." in resolved else int(resolved)
                    )
                except (ValueError, TypeError):
                    result[key] = resolved
            elif ftype == "boolean":
                result[key] = resolved.lower() not in ("false", "0", "no", "")
            else:  # string (default)
                result[key] = resolved

    return result


def _to_flat_string_dict(fields: list, node_outputs: dict) -> dict[str, str]:
    """
    Flatten a JsonValueBuilderField list to a simple ``{key: str}`` mapping.

    Used for query parameters and HTTP headers, which must always be flat
    strings.  Nested objects are JSON-serialised; arrays are likewise
    JSON-serialised.
    """
    result: dict[str, str] = {}
    for field in (fields or []):
        key = (field.get("key") or "").strip()
        if not key:
            continue
        ftype = field.get("type", "string")

        if ftype == "object":
            nested = _build_json_from_value_fields(
                field.get("fields", []), node_outputs
            )
            result[key] = _json.dumps(nested)
        elif ftype == "array":
            raw      = field.get("value") or ""
            resolved = resolve_variables(raw, node_outputs)
            try:
                parsed = _json.loads(resolved)
                result[key] = _json.dumps(
                    parsed if isinstance(parsed, list) else [parsed]
                )
            except Exception:
                result[key] = resolved
        else:
            raw      = field.get("value") or ""
            result[key] = resolve_variables(raw, node_outputs)

    return result


def _resolve_field_config(
    raw_config: Any,
    node_outputs: dict,
    flat: bool = False,
) -> dict:
    """
    Normalise a field config value from either supported format:

    • Old KV list (backward compat): ``[{"key": str, "value": str}]``
    • New JsonValueBuilder envelope: ``{"mode": "visual", "fields": [...]}``

    When ``flat=True`` (query params, headers) the result is always a
    ``dict[str, str]`` where every value is a plain string.
    When ``flat=False`` (payload body) the result is a fully-typed nested dict.
    """
    # ── New JsonValueBuilder format ────────────────────────────────────────────
    if isinstance(raw_config, dict) and raw_config.get("mode") == "visual":
        fields = raw_config.get("fields", [])
        if flat:
            return _to_flat_string_dict(fields, node_outputs)
        return _build_json_from_value_fields(fields, node_outputs)

    # ── Legacy KV list format (backward compat) ────────────────────────────────
    if isinstance(raw_config, list):
        result: dict[str, str] = {}
        for row in raw_config:
            key = (row.get("key") or "").strip()
            val = str(row.get("value") or "")
            if not key:
                continue
            result[key] = resolve_variables(val, node_outputs)
        return result

    return {}


# ─── Handler ──────────────────────────────────────────────────────────────────

class HttpRequestHandler(NodeHandler):
    """
    Make an outbound HTTP request and surface the response as node output.

    Variable resolution is applied to the URL and to every value inside the
    query_params, headers, and payload builders before the request is sent.
    """

    def execute(self, config: dict, context) -> dict:
        outputs = context.node_outputs

        # ── Resolve URL ────────────────────────────────────────────────────────
        url = resolve_variables(config.get("url", ""), outputs).strip()
        if not url:
            logger.error(
                "[FUSE] http_request: URL is empty — workflow=%s run=%s",
                context.workflow_id, context.run_id,
            )
            return {
                "success": False, "status_code": 0, "body": None,
                "error": "URL is empty or resolved to an empty string.",
            }

        # ── Method ────────────────────────────────────────────────────────────
        method = (config.get("method") or "GET").upper()

        # ── Query params (always flat strings) ────────────────────────────────
        params = _resolve_field_config(
            config.get("query_params"), outputs, flat=True
        )

        # ── Headers (always flat strings) ─────────────────────────────────────
        headers = _resolve_field_config(
            config.get("headers"), outputs, flat=True
        )

        # ── Payload body (full typed JSON dict) ───────────────────────────────
        payload_dict = _resolve_field_config(
            config.get("payload"), outputs, flat=False
        )

        # ── Timeout ───────────────────────────────────────────────────────────
        try:
            timeout = float(config.get("timeout") or _DEFAULT_TIMEOUT)
            if timeout <= 0:
                timeout = _DEFAULT_TIMEOUT
        except (TypeError, ValueError):
            timeout = _DEFAULT_TIMEOUT

        logger.info(
            "[FUSE] http_request — method=%s url=%s params_keys=%s "
            "workflow=%s run=%s",
            method, url, list(params.keys()),
            context.workflow_id, context.run_id,
        )

        # ── Execute request ────────────────────────────────────────────────────
        try:
            with httpx.Client(timeout=timeout, follow_redirects=True) as client:
                send_body = method in ("POST", "PUT", "PATCH") and payload_dict
                resp = client.request(
                    method,
                    url,
                    params=params or None,
                    headers=headers or None,
                    json=payload_dict if send_body else None,
                )
        except httpx.TimeoutException as exc:
            logger.warning(
                "[FUSE] http_request: timed out after %.1fs — url=%s "
                "workflow=%s run=%s",
                timeout, url, context.workflow_id, context.run_id,
            )
            return {
                "success": False,
                "status_code": 0,
                "body": None,
                "error": f"Request timed out after {timeout}s: {exc}",
            }
        except Exception as exc:
            logger.exception(
                "[FUSE] http_request: unexpected error — url=%s "
                "workflow=%s run=%s",
                url, context.workflow_id, context.run_id,
            )
            return {
                "success": False,
                "status_code": 0,
                "body": None,
                "error": str(exc),
            }

        status_code = resp.status_code
        success     = 200 <= status_code < 300

        # ── Parse response body ────────────────────────────────────────────────
        raw = resp.content[:_MAX_RESPONSE_BYTES]
        try:
            body: Any = resp.json()
        except Exception:
            body = raw.decode("utf-8", errors="replace")

        logger.info(
            "[FUSE] http_request: status=%s success=%s workflow=%s run=%s",
            status_code, success, context.workflow_id, context.run_id,
        )

        # ── Build output ───────────────────────────────────────────────────────
        return {
            "status_code": status_code,
            "success":     success,
            "body":        body,
        }
