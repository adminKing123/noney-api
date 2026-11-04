"""cron-job.org timezone ids (from temp/timezones.txt via scripts/extract_cron_job_org_timezones.py)."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

_ALIASES: dict[str, str] = {
    "Asia/Calcutta": "Asia/Kolkata",
    "Europe/Kiev": "Europe/Kyiv",
    "America/Godthab": "America/Nuuk",
}

_DATA_FILE = Path(__file__).resolve().parent / "data" / "cron_job_org_timezones.json"


@lru_cache(maxsize=1)
def _allowed_set() -> frozenset[str]:
    data = json.loads(_DATA_FILE.read_text(encoding="utf-8"))
    return frozenset(data.get("timezones") or [])


def normalize_cron_org_timezone(tz: str | None) -> str:
    name = (tz or "").strip()
    if not name:
        return "UTC"
    allowed = _allowed_set()
    if name in allowed:
        return name
    mapped = _ALIASES.get(name)
    if mapped and mapped in allowed:
        return mapped
    return "UTC"


def is_valid_cron_org_timezone(tz: str | None) -> bool:
    name = (tz or "").strip()
    if not name:
        return False
    allowed = _allowed_set()
    return name in allowed or _ALIASES.get(name) in allowed
