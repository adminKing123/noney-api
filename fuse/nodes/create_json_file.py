"""
fuse/nodes/create_json_file.py
==============================
Parse JSON from a textarea (with {{variable}} support), upload to CDN storage,
and expose the public download URL plus file metadata.

Output
------
{
    "success":       bool,
    "url":           str,
    "filename":      str,
    "path":          str,
    "size_bytes":    int,
    "content_type":  str,
    "original_name": str,
}
"""

from __future__ import annotations

import json
import logging

from .base import NodeHandler
from ..cdn_upload import upload_bytes_to_cdn
from ..variable_resolver import resolve_variables

logger = logging.getLogger(__name__)


class CreateJsonFileHandler(NodeHandler):
    node_type = "create_json_file"

    def execute(self, config: dict, context) -> dict:
        outputs = context.node_outputs

        raw_filename = resolve_variables(
            (config.get("filename") or "export.json").strip(),
            outputs,
        )
        raw_json = resolve_variables(
            (config.get("json_content") or "").strip(),
            outputs,
        )

        if not raw_json:
            raise ValueError("JSON content is empty — enter valid JSON in the textarea.")

        try:
            parsed = json.loads(raw_json)
        except json.JSONDecodeError as exc:
            raise ValueError(f"JSON content is not valid JSON: {exc}") from exc

        try:
            text = json.dumps(parsed, ensure_ascii=False, default=str)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"JSON content could not be serialized: {exc}") from exc

        content_bytes = text.encode("utf-8")

        try:
            meta = upload_bytes_to_cdn(
                owner_id=context.owner_id,
                filename=raw_filename,
                content=content_bytes,
            )
        except (RuntimeError, ValueError) as exc:
            raise RuntimeError(
                f"Failed to upload JSON file to CDN: {exc}"
            ) from exc

        logger.info(
            "[FUSE] create_json_file — workflow=%s run=%s url=%s size=%d",
            context.workflow_id,
            context.run_id,
            meta["url"],
            meta["size_bytes"],
        )

        return {
            "success": True,
            "content_type": "application/json",
            "original_name": raw_filename,
            **meta,
        }
