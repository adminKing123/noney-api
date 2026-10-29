"""
fuse/schema_utils.py
====================
Normalize and enrich body_builder / response_schema / output_schema configs
produced by AI workflow generation.

The FormBuilder BodyBuilderField expects:
    {
        "mode": "visual",
        "rootType": "object|array|string|number|boolean",  # default object
        "fields": [...],       # when rootType === object
        "items": {...},        # when rootType === array (schema)
        "elements": [...],     # when rootType === array (json_value_builder)
        "value": str,          # primitive roots (json_value_builder)
    }
"""

from __future__ import annotations

import json
import re
from typing import Any

VALID_FIELD_TYPES = frozenset({"string", "number", "boolean", "array", "object"})

_TYPE_ALIASES = {
    "str": "string",
    "text": "string",
    "integer": "number",
    "int": "number",
    "float": "number",
    "double": "number",
    "bool": "boolean",
    "list": "array",
    "dict": "object",
}

# {{ref.body.fieldName}} — webhook incoming body
_BODY_PATH_RE = re.compile(r"\{\{([^.}]+)\.body\.([a-zA-Z_][\w]*)\}\}")

# {{ref.fieldName}} — flattened output from http / ai nodes (first segment after ref)
_DIRECT_FIELD_RE = re.compile(r"\{\{([^.}]+)\.([a-zA-Z_][\w]*)\}\}")

_SCHEMA_KEYS_BY_NODE_TYPE = {
    "webhook":              "body_schema",
    "http_request":         "response_schema",
    "ai_structured_output": "output_schema",
}


def coerce_field_type(raw_type: Any) -> str:
    if raw_type is None:
        return "string"
    t = str(raw_type).lower().strip()
    t = _TYPE_ALIASES.get(t, t)
    return t if t in VALID_FIELD_TYPES else "string"


def coerce_root_type(raw_type: Any) -> str:
    """JSON root type for body_builder / json_value_builder envelopes."""
    t = coerce_field_type(raw_type or "object")
    return t if t in VALID_FIELD_TYPES else "object"


def _normalize_array_items(raw_items: Any) -> dict:
    items = raw_items if isinstance(raw_items, dict) else {}
    item_type = coerce_field_type(items.get("type"))
    normalized: dict[str, Any] = {"type": item_type}
    if item_type == "object":
        nested = items.get("fields") or items.get("properties")
        if isinstance(nested, list):
            normalized["fields"] = [
                f for item in nested
                if (f := normalize_field_node(item)) is not None
            ]
        elif isinstance(nested, dict):
            normalized["fields"] = [
                normalized
                for k, v in nested.items()
                if (normalized := normalize_field_node(
                    v if isinstance(v, dict) else {"type": v},
                    fallback_key=k,
                )) is not None
            ]
        else:
            normalized["fields"] = []
    return normalized


def _attach_root_type(envelope: dict, raw: dict | None) -> dict:
    root = coerce_root_type((raw or {}).get("rootType"))
    envelope["rootType"] = root
    if root == "array":
        envelope["items"] = _normalize_array_items((raw or {}).get("items"))
    elif root in ("string", "number", "boolean"):
        if isinstance(raw, dict) and raw.get("value") is not None:
            envelope["value"] = str(raw.get("value"))
    return envelope


def normalize_field_node(raw: Any, *, fallback_key: str = "") -> dict | None:
    """Normalize a single schema field row. Returns None if no key can be resolved."""
    if isinstance(raw, str):
        key = fallback_key.strip()
        return {"key": key, "type": coerce_field_type(raw)} if key else None

    if not isinstance(raw, dict):
        return None

    key = (
        raw.get("key")
        or raw.get("name")
        or raw.get("field")
        or raw.get("field_name")
        or raw.get("fieldName")
        or fallback_key
        or ""
    )
    key = str(key).strip()
    if not key:
        return None

    field_type = coerce_field_type(
        raw.get("type")
        or raw.get("field_type")
        or raw.get("fieldType")
        or raw.get("data_type")
        or raw.get("dataType")
    )

    field: dict[str, Any] = {"key": key, "type": field_type}

    if raw.get("description"):
        field["description"] = str(raw["description"])
    if raw.get("enum"):
        field["enum"] = str(raw["enum"])

    if field_type == "object":
        nested = raw.get("fields") or raw.get("properties")
        if isinstance(nested, list):
            field["fields"] = [
                f for item in nested
                if (f := normalize_field_node(item)) is not None
            ]
        elif isinstance(nested, dict):
            field["fields"] = [
                normalized
                for k, v in nested.items()
                if (normalized := normalize_field_node(
                    v if isinstance(v, dict) else {"type": v},
                    fallback_key=k,
                )) is not None
            ]

    if field_type == "array":
        field["items"] = _normalize_array_items(raw.get("items"))

    return field


def normalize_body_builder(value: Any) -> dict:
    """
    Coerce any AI-produced schema value into BodyBuilderField storage shape.
    """
    if value is None or value == "":
        return {"mode": "visual", "rootType": "object", "fields": []}

    if isinstance(value, list):
        fields = [
            f for item in value
            if (f := normalize_field_node(item)) is not None
        ]
        return _attach_root_type({"mode": "visual", "fields": fields}, None)

    if not isinstance(value, dict):
        return {"mode": "visual", "rootType": "object", "fields": []}

    raw_root = value.get("rootType")

    if "fields" in value:
        fields = [
            f for item in (value.get("fields") or [])
            if (f := normalize_field_node(item)) is not None
        ]
        return _attach_root_type({"mode": "visual", "fields": fields}, value)

    if "properties" in value and isinstance(value["properties"], dict):
        fields = [
            normalize_field_node(prop, fallback_key=key)
            for key, prop in value["properties"].items()
        ]
        envelope = {
            "mode": "visual",
            "fields": [f for f in fields if f is not None],
        }
        return _attach_root_type(envelope, value)

    # Flat map: { "email": "string", "count": { "type": "number" } }
    skip_keys = frozenset({
        "mode", "presets", "sections", "type", "properties",
        "rootType", "items", "elements", "value",
    })
    fields: list[dict] = []
    for key, val in value.items():
        if key in skip_keys:
            continue
        if isinstance(val, str):
            fields.append({"key": key, "type": coerce_field_type(val)})
        elif isinstance(val, dict):
            normalized = normalize_field_node({**val, "key": key})
            if normalized:
                fields.append(normalized)

    envelope = {"mode": "visual", "fields": fields}
    if raw_root is None and not fields and value.get("items"):
        envelope = _attach_root_type({"mode": "visual", "fields": []}, {**value, "rootType": "array"})
    else:
        envelope = _attach_root_type(envelope, value)
    return envelope


def _empty_json_value_envelope(root: str = "object") -> dict:
    root = coerce_root_type(root)
    envelope: dict[str, Any] = {"mode": "visual", "rootType": root}
    if root == "object":
        envelope["fields"] = []
    elif root == "array":
        envelope["elements"] = []
    else:
        envelope["value"] = ""
    return envelope


def normalize_json_value_builder(value: Any) -> dict:
    """Coerce json_value_builder config; defaults rootType to object."""
    if value is None or value == "":
        return _empty_json_value_envelope("object")

    if isinstance(value, list):
        return {
            "mode": "visual",
            "rootType": "object",
            "fields": [
                {"key": (row.get("key") or "").strip(), "type": "string", "value": str(row.get("value") or "")}
                for row in value
                if isinstance(row, dict) and (row.get("key") or "").strip()
            ],
        }

    if not isinstance(value, dict):
        return _empty_json_value_envelope("object")

    root = coerce_root_type(value.get("rootType"))
    envelope = _empty_json_value_envelope(root)
    if root == "object":
        fields = value.get("fields") or []
        envelope["fields"] = fields if isinstance(fields, list) else []
    elif root == "array":
        elements = value.get("elements") or []
        envelope["elements"] = elements if isinstance(elements, list) else []
    else:
        envelope["value"] = str(value.get("value") or "")

    return envelope


def _merge_schema_fields(existing: dict, inferred: list[dict]) -> dict:
    """Merge inferred fields into a normalized schema without duplicating keys."""
    schema = normalize_body_builder(existing)
    present = {(f.get("key") or "").strip() for f in schema["fields"]}

    for field in inferred:
        key = (field.get("key") or "").strip()
        if key and key not in present:
            schema["fields"].append(field)
            present.add(key)

    return schema


def _collect_variable_refs(config: Any) -> set[str]:
    """Return all {{...}} token inner strings found anywhere in config."""
    refs: set[str] = set()
    text = json.dumps(config) if not isinstance(config, str) else config
    for match in re.finditer(r"\{\{([^}]+)\}\}", text):
        refs.add(match.group(1).strip())
    return refs


def infer_schema_fields_for_node(
    node_ref: str,
    node_type: str,
    all_configs: list[tuple[str, str, dict]],
) -> list[dict]:
    """
    Infer schema fields from variable references pointing at ``node_ref``.

    ``all_configs`` is a list of (ref, node_type, config) for every node in the plan.
    """
    schema_key = _SCHEMA_KEYS_BY_NODE_TYPE.get(node_type)
    if not schema_key:
        return []

    inferred: dict[str, str] = {}

    for _ref, _type, config in all_configs:
        blob = json.dumps(config)
        for match in _BODY_PATH_RE.finditer(blob):
            source_ref, field_name = match.group(1), match.group(2)
            if source_ref == node_ref:
                inferred[field_name] = "string"

        for match in _DIRECT_FIELD_RE.finditer(blob):
            source_ref, field_name = match.group(1), match.group(2)
            if source_ref != node_ref:
                continue
            # Skip paths handled by body.* or known top-level webhook keys
            if field_name in ("body", "headers", "query_params", "method", "triggered_at"):
                continue
            if node_type == "webhook":
                continue
            inferred[field_name] = "string"

    return [{"key": k, "type": t} for k, t in sorted(inferred.items())]


def normalize_node_schemas(
    node_type: str,
    config: dict,
    schema_key_map: dict[str, str] | None = None,
) -> dict:
    """Normalize all schema-builder fields on a node config."""
    schema_key_map = schema_key_map or _SCHEMA_KEYS_BY_NODE_TYPE
    config = dict(config or {})
    schema_key = schema_key_map.get(node_type)
    if schema_key and schema_key in config:
        config[schema_key] = normalize_body_builder(config.get(schema_key))
    elif schema_key and schema_key in (config or {}):
        pass
    # Normalize any body_builder key present even if not in map
    for key, val in list(config.items()):
        if isinstance(val, dict) and ("fields" in val or "properties" in val):
            if key.endswith("_schema") or key == "body_schema":
                config[key] = normalize_body_builder(val)
    return config


def enrich_plan_node_configs(
    nodes: list,
    schema_key_map: dict[str, str] | None = None,
) -> list[dict]:
    """
    Normalize and enrich schema fields for every node in an AI workflow plan.

    Returns dicts with keys: ref, node_type, label, config.
    """
    schema_key_map = schema_key_map or _SCHEMA_KEYS_BY_NODE_TYPE
    all_configs = [(n.ref, n.node_type, n.config or {}) for n in nodes]

    enriched: list[dict] = []
    for node in nodes:
        config = normalize_node_schemas(node.node_type, node.config or {}, schema_key_map)
        schema_key = schema_key_map.get(node.node_type)
        if schema_key:
            inferred = infer_schema_fields_for_node(node.ref, node.node_type, all_configs)
            config[schema_key] = _merge_schema_fields(config.get(schema_key), inferred)
        enriched.append({
            "ref":       node.ref,
            "node_type": node.node_type,
            "label":     node.label,
            "config":    config,
        })

    return enriched


def _parse_type_clause(clause: str) -> dict[str, Any]:
    """Parse a natural-language or shorthand type description into a field spec."""
    clause_stripped = clause.strip().rstrip(".,;")
    clause_lower = clause_stripped.lower()

    if clause_lower in ("string", "str", "text"):
        return {"type": "string"}
    if clause_lower in ("number", "num", "integer", "int", "float"):
        return {"type": "number"}
    if clause_lower in ("boolean", "bool"):
        return {"type": "boolean"}

    if "array" in clause_lower:
        item_m = re.search(
            r"(?:items?\s+(?:type\s+)?(?:of\s+)?|type\s+of\s+|containing\s+items?\s+type\s+of\s+)"
            r"(string|number|boolean|object|integer|int|float)",
            clause_lower,
        )
        item_type = coerce_field_type(item_m.group(1) if item_m else "string")
        return {"type": "array", "items": {"type": item_type}}

    if "object" in clause_lower:
        fields: list[dict] = []
        props_m = re.search(r"properties?\s+as\s+(.+)", clause_stripped, re.IGNORECASE)
        if props_m:
            for segment in re.split(r"\s+and\s+", props_m.group(1)):
                seg_m = re.match(r"([a-zA-Z_]\w*)\s*:\s*(\w+)", segment.strip())
                if seg_m:
                    fields.append({
                        "key": seg_m.group(1),
                        "type": coerce_field_type(seg_m.group(2)),
                    })
        return {"type": "object", "fields": fields}

    return {"type": coerce_field_type(clause_stripped)}


def parse_schema_fields_from_prompt(prompt: str) -> list[dict]:
    """
    Extract explicit ``field: type`` lines from a user prompt, including nested
    array/object descriptions.
    """
    search_text = prompt
    for marker in (
        r"body\s+fields?\s+schema",
        r"incoming\s+body",
        r"fields?\s+schema\s+is\s+given",
        r"schema\s+is\s+given\s+below",
    ):
        m = re.search(marker + r"[\s:]*([\s\S]+)", prompt, re.IGNORECASE)
        if m:
            search_text = m.group(1)[:3000]
            break

    fields_by_key: dict[str, dict] = {}

    for line in search_text.splitlines():
        line = line.strip()
        if not line:
            continue
        m = re.match(r"^([a-zA-Z_]\w*)\s*:\s*(.+)$", line)
        if not m:
            continue
        key, clause = m.group(1), m.group(2).strip()
        if len(clause.split()) > 15 and "array" not in clause.lower() and "object" not in clause.lower():
            continue
        type_info = _parse_type_clause(clause)
        normalized = normalize_field_node({"key": key, **type_info})
        if normalized:
            fields_by_key[key] = normalized

    return list(fields_by_key.values())


def parse_webhook_hints_from_prompt(prompt: str) -> dict[str, Any]:
    """Extract webhook method, auth, secret, and response code from the prompt."""
    hints: dict[str, Any] = {}
    pl = prompt.lower()

    if re.search(r"\bpost\b", pl):
        hints["method"] = "POST"
    elif re.search(r"\bget\b", pl) and "method" in pl:
        hints["method"] = "GET"

    if "bearer" in pl:
        hints["auth_type"] = "bearer"
    elif "basic auth" in pl or "basic" in pl and "auth" in pl:
        hints["auth_type"] = "basic"
    elif "hmac" in pl:
        hints["auth_type"] = "hmac"

    secret_m = re.search(
        r"(?:secr[eai]t|token)\s+(?:token\s+)?is\s+(\S+)",
        prompt,
        re.IGNORECASE,
    )
    if secret_m:
        hints["secret"] = secret_m.group(1).rstrip(".,;")

    status_m = re.search(
        r"(?:response\s+)?status\s+code\s+(?:is\s+|we\s+want\s+(?:is\s+)?)?(\d{3})",
        prompt,
        re.IGNORECASE,
    )
    if status_m:
        hints["response_code"] = int(status_m.group(1))

    return hints


_EMAIL_RE = re.compile(r"[\w.+-]+@[\w.-]+\.\w+")


def parse_email_from_prompt(prompt: str) -> str | None:
    m = _EMAIL_RE.search(prompt)
    return m.group(0) if m else None


def _set_schema_fields(config: dict, schema_key: str, fields: list[dict]) -> None:
    normalized = [
        f for field in fields
        if (f := normalize_field_node(field)) is not None
    ]
    config[schema_key] = {"mode": "visual", "rootType": "object", "fields": normalized}


def apply_user_prompt_hints(user_prompt: str, nodes: list) -> list[dict]:
    """
    Override AI-generated configs with explicit values parsed from the user prompt.
    User-specified schema types always win over AI defaults.
    """
    schema_fields = parse_schema_fields_from_prompt(user_prompt)
    webhook_hints = parse_webhook_hints_from_prompt(user_prompt)
    email = parse_email_from_prompt(user_prompt)

    enriched: list[dict] = []
    webhook_ref: str | None = None

    for node in nodes:
        if node.node_type == "webhook":
            webhook_ref = node.ref

    for node in nodes:
        config = dict(node.config or {})

        if node.node_type == "webhook":
            config.update(webhook_hints)
            if schema_fields:
                _set_schema_fields(config, "body_schema", schema_fields)

        if node.node_type == "ai_structured_output" and webhook_ref:
            if not (config.get("prompt") or "").strip():
                config["prompt"] = (
                    f"Analyze and summarize the following webhook payload:\n"
                    f"{{{{{webhook_ref}.body}}}}"
                )
            if not schema_has_valid_fields(config, "output_schema"):
                _set_schema_fields(config, "output_schema", [
                    {"key": "summary", "type": "string", "description": "Concise summary of the payload"},
                ])

        if node.node_type == "send_gmail":
            if email:
                config["to"] = email
            ai_refs = [n.ref for n in nodes if n.node_type == "ai_structured_output"]
            if ai_refs and not (config.get("body") or "").strip():
                config["body"] = f"{{{{{ai_refs[0]}.summary}}}}"
            if not (config.get("subject") or "").strip():
                config["subject"] = "Workflow Summary"

        config = normalize_node_schemas(node.node_type, config)
        enriched.append({
            "ref":       node.ref,
            "node_type": node.node_type,
            "label":     node.label,
            "config":    config,
        })

    return enriched


def build_prompt_extras(user_prompt: str) -> str:
    """Build additional instructions injected into the AI user message."""
    parts: list[str] = []
    schema_fields = parse_schema_fields_from_prompt(user_prompt)
    webhook_hints = parse_webhook_hints_from_prompt(user_prompt)
    email = parse_email_from_prompt(user_prompt)

    if schema_fields:
        parts.append(
            "## User-specified body schema — copy EXACTLY into webhook body_schema "
            "(preserve number, boolean, array, and object types with nested structure):\n"
            f"```json\n{json.dumps(schema_fields, indent=2)}\n```"
        )
    if webhook_hints:
        parts.append(
            "## User-specified webhook settings — apply to the webhook starter node:\n"
            f"```json\n{json.dumps(webhook_hints, indent=2)}\n```"
        )
    if email:
        parts.append(f"## User-specified email recipient: {email}")

    return "\n\n".join(parts)


def schema_has_valid_fields(config: dict, schema_key: str) -> bool:
    schema = normalize_body_builder(config.get(schema_key))
    root = schema.get("rootType") or "object"
    if root != "object":
        return True
    return any(
        (f.get("key") or "").strip() and f.get("type")
        for f in schema.get("fields") or []
    )
