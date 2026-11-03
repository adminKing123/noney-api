"""
utils/cron_service.py
---------------------
Register / remove Fuse schedules via the external Cron Service HTTP API.
"""

from __future__ import annotations

import logging

import requests

from config import CONFIG

logger = logging.getLogger(__name__)


def is_cron_service_configured() -> bool:
    host = CONFIG.CRON_SERVICE.HOST
    api_key = CONFIG.CRON_SERVICE.API_KEY
    return bool(host and api_key)


def upsert_workflow_schedule(payload: dict) -> dict | None:
    """
    Create or update a schedule in Cron Service.

    Returns parsed JSON on success, None on failure.
    """
    if not is_cron_service_configured():
        logger.error("Cron service not configured (CRON_SERVICE_HOST / CRON_SERVICE_API_KEY).")
        return None

    base = CONFIG.CRON_SERVICE.HOST.rstrip("/")
    url = f"{base}/api/schedules/upsert"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {CONFIG.CRON_SERVICE.API_KEY}",
    }
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=60)
        if resp.status_code == 200:
            return resp.json()
        logger.error(
            "Cron service upsert failed (status=%s): %s",
            resp.status_code,
            resp.text,
        )
    except requests.RequestException as exc:
        logger.error("Cron service network error: %s", exc)
    return None


def delete_workflow_schedule(workflow_id: str) -> bool:
    if not is_cron_service_configured():
        logger.warning("Cron service not configured — skip delete for %s", workflow_id)
        return False

    base = CONFIG.CRON_SERVICE.HOST.rstrip("/")
    url = f"{base}/api/schedules/{workflow_id}"
    headers = {"Authorization": f"Bearer {CONFIG.CRON_SERVICE.API_KEY}"}
    try:
        resp = requests.delete(url, headers=headers, timeout=30)
        if resp.status_code in (200, 404):
            return True
        logger.error(
            "Cron service delete failed (status=%s): %s",
            resp.status_code,
            resp.text,
        )
    except requests.RequestException as exc:
        logger.error("Cron service delete network error: %s", exc)
    return False
