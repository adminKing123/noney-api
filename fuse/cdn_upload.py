"""
fuse/cdn_upload.py
==================
Upload workflow-generated files to GitHub-backed storage and return a CDN URL.
"""

from __future__ import annotations

import uuid
from werkzeug.utils import secure_filename

from config import CONFIG
from utils.files import upload_file as github_upload_file


def upload_bytes_to_cdn(
    *,
    owner_id: str,
    filename: str,
    content: bytes,
    subfolder: str = "fuse",
) -> dict:
    """
    Store ``content`` under uploads/{subfolder}/{owner_id}/ and return metadata.

    Raises:
        ValueError: invalid or empty inputs
        RuntimeError: GitHub upload failed
    """
    if not owner_id:
        raise ValueError("Missing owner_id for CDN upload.")
    if not content:
        raise ValueError("Cannot upload an empty file.")

    raw_name = (filename or "export.json").strip()
    safe_base = secure_filename(raw_name) or "export.json"
    if not safe_base.lower().endswith(".json"):
        safe_base = f"{safe_base}.json"

    unique_name = f"{uuid.uuid4().hex[:12]}_{safe_base}"
    github_path = (
        f"{CONFIG.UPLOAD1.UPLOAD_FOLDER}/{subfolder}/{owner_id}/{unique_name}"
    )
    commit_message = f"Fuse upload {unique_name} for user {owner_id}"

    if not github_upload_file(github_path, content, commit_message):
        raise RuntimeError("CDN upload failed — check GitHub upload credentials.")

    base = (CONFIG.CDN_URL or CONFIG.HOST or "").rstrip("/")
    url = f"{base}/download/{github_path}"

    return {
        "url": url,
        "filename": unique_name,
        "path": github_path,
        "size_bytes": len(content),
    }
