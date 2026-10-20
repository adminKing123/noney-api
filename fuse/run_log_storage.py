"""
fuse/run_log_storage.py
=======================
Keep fuse_run_logs Firestore documents under the 1 MiB limit by offloading
large output / input / config / variables payloads to CDN as JSON files.
"""

from __future__ import annotations

import copy
import json
import logging
from typing import Any

from fuse.cdn_upload import upload_bytes_to_cdn

logger = logging.getLogger(__name__)

# Target max serialized document size (headroom under Firestore 1 MiB cap)
SAFE_DOC_BYTES = 850_000
# Inline field budget before offloading to CDN
MAX_INLINE_FIELD_BYTES = 120_000

_OFFLOAD_SENTINEL = "_offloaded"


def _serialized_size(obj: Any) -> int:
    if obj is None:
        return 0
    try:
        return len(
            json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8")
        )
    except (TypeError, ValueError):
        return len(repr(obj).encode("utf-8"))


def _is_offloaded_ref(obj: Any) -> bool:
    return isinstance(obj, dict) and obj.get(_OFFLOAD_SENTINEL) is True and bool(
        obj.get("url")
    )


def _offload_to_cdn(
    value: Any,
    *,
    owner_id: str,
    run_id: str,
    node_id: str,
    field: str,
) -> dict:
    payload = json.dumps(value, ensure_ascii=False, default=str).encode("utf-8")
    meta = upload_bytes_to_cdn(
        owner_id=owner_id,
        filename=f"{run_id}_{node_id}_{field}.json",
        content=payload,
        subfolder="fuse/run_logs",
    )
    return {
        _OFFLOAD_SENTINEL: True,
        "field": field,
        "url": meta["url"],
        "path": meta["path"],
        "filename": meta["filename"],
        "size_bytes": meta["size_bytes"],
    }


def _maybe_offload_field(
    value: Any,
    *,
    owner_id: str,
    run_id: str,
    node_id: str,
    field: str,
    force: bool = False,
) -> Any:
    if value is None or _is_offloaded_ref(value):
        return value
    size = _serialized_size(value)
    if not force and size <= MAX_INLINE_FIELD_BYTES:
        return value
    try:
        return _offload_to_cdn(
            value,
            owner_id=owner_id,
            run_id=run_id,
            node_id=node_id,
            field=field,
        )
    except Exception:
        logger.exception(
            "[FUSE] Failed to offload run log field — run=%s node=%s field=%s",
            run_id,
            node_id,
            field,
        )
        return {
            _OFFLOAD_SENTINEL: True,
            "field": field,
            "error": "Payload too large to store inline and CDN offload failed.",
            "approx_bytes": size,
        }


def _sanitize_create_json_file_log(data: dict) -> None:
    """Shrink Create JSON log fields — output is metadata-only; omit bulky config."""
    output = data.get("output")
    if isinstance(output, dict):
        allowed = (
            "success",
            "url",
            "filename",
            "path",
            "size_bytes",
            "content_type",
            "original_name",
        )
        data["output"] = {k: output[k] for k in allowed if k in output}

    config = data.get("config")
    if isinstance(config, dict) and "json_content" in config:
        raw = config.get("json_content")
        preview = raw[:240] if isinstance(raw, str) else None
        config = copy.deepcopy(config)
        config["json_content"] = {
            "_omitted_from_run_log": True,
            "hint": "Full JSON textarea omitted from run history (see uploaded file URL in output).",
            "preview": preview,
        }
        data["config"] = config


def prepare_run_log_document(
    data: dict,
    *,
    owner_id: str,
    run_id: str,
    node_id: str,
    node_type: str = "",
) -> dict:
    """
    Return a copy of ``data`` safe to persist in Firestore (may contain CDN refs).
    """
    doc = copy.deepcopy(data)

    if node_type == "create_json_file":
        _sanitize_create_json_file_log(doc)

    for field in ("output", "input", "config", "variables"):
        if field not in doc or doc[field] is None:
            continue
        doc[field] = _maybe_offload_field(
            doc[field],
            owner_id=owner_id,
            run_id=run_id,
            node_id=node_id,
            field=field,
        )

    # If the full document is still too large, force-offload largest fields first.
    priority = ("input", "variables", "config", "output")
    while _serialized_size(doc) > SAFE_DOC_BYTES:
        offloaded_any = False
        for field in priority:
            val = doc.get(field)
            if val is None or _is_offloaded_ref(val):
                continue
            doc[field] = _maybe_offload_field(
                val,
                owner_id=owner_id,
                run_id=run_id,
                node_id=node_id,
                field=field,
                force=True,
            )
            offloaded_any = True
            if _serialized_size(doc) <= SAFE_DOC_BYTES:
                break
        if not offloaded_any:
            logger.warning(
                "[FUSE] Run log still oversized after offload — run=%s node=%s size=%d",
                run_id,
                node_id,
                _serialized_size(doc),
            )
            break

    return doc


def is_firestore_document_too_large(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return "exceeds the maximum allowed size" in msg or "maximum allowed size" in msg


def emergency_minimal_run_log(data: dict, node_type: str = "") -> dict:
    """
    Last-resort shrink when Firestore still rejects the document after CDN offload.
    Keeps status, timing, errors, and small output metadata only.
    """
    doc = copy.deepcopy(data)
    doc.pop("input", None)
    doc.pop("config", None)
    doc.pop("variables", None)
    if node_type == "create_json_file":
        _sanitize_create_json_file_log(doc)
    out = doc.get("output")
    if out is not None and not _is_offloaded_ref(out):
        if _serialized_size(out) > MAX_INLINE_FIELD_BYTES:
            doc["output"] = {
                "_note": "Output omitted after Firestore size limit.",
                **(
                    {k: out[k] for k in ("success", "url", "error") if k in out}
                    if isinstance(out, dict)
                    else {}
                ),
            }
    doc["_log_storage_fallback"] = "minimal_after_size_error"
    return doc
