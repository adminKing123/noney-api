import hashlib
import hmac as _hmac
import logging
import re
import secrets

import requests
from datetime import datetime, timedelta
from db import db
from config import CONFIG

logger = logging.getLogger(__name__)

WEBEX_TOKEN_URL = f"{CONFIG.WEBEX_API_BASE.rstrip('/')}/access_token"


def refresh_webex_access_token_if_expired(user_id: str, integration: dict) -> dict | None:
    """Checks if the access token is expired and refreshes it if needed for Webex."""
    expires_at_str = integration.get("expires_at")
    if not expires_at_str:
        return integration

    expires_at = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
    if datetime.utcnow().replace(tzinfo=None) < expires_at.replace(tzinfo=None):
        return integration

    refresh_token = integration.get("refresh_token")
    if not refresh_token:
        print("No refresh token available for Webex integration.")
        return None

    data = {
        "client_id": CONFIG.WEBEX_OAUTH_CLIENT_ID,
        "client_secret": CONFIG.WEBEX_OAUTH_CLIENT_SECRET,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }
    response = requests.post(WEBEX_TOKEN_URL, data=data)
    if response.status_code != 200:
        print(f"Failed to refresh Webex token: {response.text}")
        return None

    token_data = response.json()
    new_expires_in = token_data.get("expires_in", 1209600)
    new_expires_at = (datetime.utcnow() + timedelta(seconds=new_expires_in)).isoformat() + "Z"

    updated_tokens = {
        "access_token": token_data.get("access_token"),
        "refresh_token": token_data.get("refresh_token", refresh_token),
        "expires_at": new_expires_at,
    }

    refresh_token_expires_in = token_data.get("refresh_token_expires_in")
    if refresh_token_expires_in:
        updated_tokens["refresh_token_expires_at"] = (
            datetime.utcnow() + timedelta(seconds=refresh_token_expires_in)
        ).isoformat() + "Z"

    db.integration.save_integration_tokens(user_id, "webex", updated_tokens)
    print(f"[Webex Refresh] Token refreshed for user {user_id}. New expires_at: {new_expires_at}")
    return {**integration, **updated_tokens}


def get_webex_access_token(user_id: str, integration: dict | None = None) -> str | None:
    """Return a valid Webex access token, refreshing if needed."""
    integration = integration or db.integration.get_integration(user_id, "webex")
    if not integration:
        return None
    integration = refresh_webex_access_token_if_expired(user_id, integration)
    if not integration:
        return None
    return integration.get("access_token")


def build_webex_message_filter(config: dict) -> str | None:
    """Build the Webex webhook filter string from starter node config."""
    filter_type = (config.get("filter_type") or "all").lower()
    if filter_type == "room":
        room_id = (config.get("room_id") or "").strip()
        return f"roomId={room_id}" if room_id else None
    if filter_type == "direct":
        return "roomType=direct"
    return None


def create_message_webhook(
    access_token: str,
    *,
    target_url: str,
    name: str,
    filter_str: str | None = None,
    secret: str | None = None,
) -> dict:
    """Register a Webex webhook for new messages. Returns {id, secret, ...}.

    Webex does not echo ``secret`` in the create response — it must be supplied
    in the request body. We generate one when omitted and return it alongside
    the webhook id from the API response.
    """
    webhook_secret = secret or secrets.token_urlsafe(32)
    payload = {
        "name": name,
        "targetUrl": target_url,
        "resource": "messages",
        "event": "created",
        "secret": webhook_secret,
    }
    if filter_str:
        payload["filter"] = filter_str

    response = requests.post(
        f"{CONFIG.WEBEX_API_BASE}/webhooks",
        headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
        json=payload,
        timeout=30,
    )
    if response.status_code not in (200, 201):
        raise RuntimeError(f"Failed to create Webex webhook: {response.text}")

    data = response.json()
    webhook_id = data.get("id")
    if not webhook_id:
        raise RuntimeError("Webex webhook response missing id.")
    return {**data, "id": webhook_id, "secret": webhook_secret}


def delete_webhooks_for_target_url(
    access_token: str,
    target_url: str,
    *,
    keep_id: str | None = None,
) -> int:
    """
    Remove duplicate Webex webhooks pointing at the same Fuse URL.

    Orphan webhooks (e.g. after a failed deactivate) can still deliver events
    signed with an old secret while the workflow expects a newer one — those
    deliveries fail with 401 intermittently.
    """
    normalized = (target_url or "").rstrip("/")
    if not normalized:
        return 0

    removed = 0
    for wh in list_all_webhooks(access_token):
        url = (wh.get("targetUrl") or "").rstrip("/")
        if url != normalized:
            continue
        webhook_id = wh.get("id")
        if not webhook_id or webhook_id == keep_id:
            continue
        if delete_webhook(access_token, webhook_id):
            removed += 1
            logger.info(
                "[Webex] Removed duplicate webhook %s for target %s",
                webhook_id,
                normalized,
            )
    return removed


def delete_webhook(access_token: str, webhook_id: str) -> bool:
    """Delete a Webex webhook by ID. Returns True if deleted or already gone."""
    if not webhook_id:
        return False
    response = requests.delete(
        f"{CONFIG.WEBEX_API_BASE}/webhooks/{webhook_id}",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=30,
    )
    if response.status_code in (200, 204, 404):
        return True
    logger.warning("Failed to delete Webex webhook %s: %s", webhook_id, response.text)
    return False


def cleanup_webex_workflow_webhook(owner_id: str, compiled_graph: dict | None) -> bool:
    """
    Delete the Webex message webhook registered for a workflow, if any.

    Uses the webhook ID stored in ``compiled_graph["webex_webhook"]`` so cleanup
    works even when the workflow is not loaded in the in-memory runtime (e.g.
    inactive workflows or after a server restart).

    Returns True when a webhook ID was found and a delete was attempted.
    """
    if not compiled_graph:
        return False

    starter = compiled_graph.get("starter") or {}
    if starter.get("node_type") != "webex_message":
        return False

    webhook_id = (compiled_graph.get("webex_webhook") or {}).get("id")
    if not webhook_id:
        return False

    access_token = get_webex_access_token(owner_id)
    if not access_token:
        logger.warning(
            "[Webex] Cannot delete webhook %s — no access token for user %s",
            webhook_id,
            owner_id,
        )
        return False

    deleted = delete_webhook(access_token, webhook_id)
    if deleted:
        logger.info("[Webex] Removed webhook %s during workflow cleanup", webhook_id)
    return deleted


def _parse_webex_next_url(link_header: str | None) -> str | None:
    """Extract the RFC5988 ``rel=next`` URL from a Webex Link response header."""
    if not link_header:
        return None
    for part in link_header.split(","):
        if 'rel="next"' not in part and "rel=next" not in part:
            continue
        match = re.search(r"<([^>]+)>", part)
        if match:
            return match.group(1)
    return None


def _paginate_webex_collection(
    access_token: str,
    collection: str,
    *,
    max_per_page: int = 100,
) -> list[dict]:
    """Fetch all pages of a Webex list endpoint (webhooks, rooms, etc.)."""
    items: list[dict] = []
    url: str | None = f"{CONFIG.WEBEX_API_BASE.rstrip('/')}/{collection.lstrip('/')}"
    params: dict | None = {"max": max_per_page}

    while url:
        response = requests.get(
            url,
            headers={"Authorization": f"Bearer {access_token}"},
            params=params,
            timeout=30,
        )
        if response.status_code != 200:
            raise RuntimeError(f"Failed to list Webex {collection}: {response.text}")

        payload = response.json()
        items.extend(payload.get("items") or [])

        url = _parse_webex_next_url(response.headers.get("Link"))
        params = None

    return items


def list_all_webhooks(access_token: str, *, max_per_page: int = 100) -> list[dict]:
    """
    List every webhook for the authenticated user, following Webex pagination.

    Webex paginates via RFC5988 Link headers; most accounts have only a handful
    of webhooks (typically one per active Fuse workflow).
    """
    return _paginate_webex_collection(access_token, "webhooks", max_per_page=max_per_page)


def list_all_rooms(access_token: str, *, max_per_page: int = 100) -> list[dict]:
    """List every room/space the authenticated user can access."""
    return _paginate_webex_collection(access_token, "rooms", max_per_page=max_per_page)


def list_all_people(access_token: str, *, max_per_page: int = 100) -> list[dict]:
    """List people visible to the authenticated user."""
    return _paginate_webex_collection(access_token, "people", max_per_page=max_per_page)


def serialize_room_for_ui(item: dict) -> dict:
    """Return a UI-friendly room summary for dropdowns."""
    room_type = item.get("type") or "group"
    title = item.get("title") or "Untitled space"
    type_label = "Direct" if room_type == "direct" else "Space"
    return {
        "id":    item.get("id"),
        "title": title,
        "type":  room_type,
        "label": f"{title} ({type_label})",
    }


def serialize_person_for_ui(item: dict) -> dict | None:
    """Return a UI-friendly person summary for dropdowns."""
    person_id = item.get("id")
    if not person_id:
        return None

    emails = item.get("emails") or []
    email = emails[0] if emails else ""
    display = item.get("displayName") or email or person_id

    return {
        "id":           person_id,
        "email":        email,
        "display_name": display,
        "label_email":  f"{display} ({email})" if email else None,
        "label_id":     f"{display}",
    }


def serialize_webhook_for_ui(item: dict) -> dict:
    """Return a safe, UI-friendly webhook summary."""
    target_url = item.get("targetUrl") or ""
    return {
        "id":         item.get("id"),
        "name":       item.get("name"),
        "target_url": target_url,
        "resource":   item.get("resource"),
        "event":      item.get("event"),
        "filter":     item.get("filter"),
        "status":     item.get("status"),
        "created":    item.get("created"),
        "is_fuse_managed": "/fuse/webex/webhook/" in target_url,
    }


def sync_fuse_workflows_after_webhook_removal(owner_id: str, webhook_id: str) -> None:
    """
    If a deleted webhook belonged to a Fuse workflow, clear stored metadata
    and deactivate the workflow so state stays consistent.
    """
    from fuse.runtime import runtime

    cursor: dict | None = None
    while True:
        kwargs: dict = {"limit": 100}
        if cursor:
            kwargs["after_created_at"] = cursor.get("after_created_at")
            kwargs["after_id"] = cursor.get("after_id")

        page = db.workflow.list_for_owner(owner_id, **kwargs)
        for wf in page.get("items") or []:
            runtime = wf.get("fuse_runtime") or {}
            legacy = wf.get("compiled_graph") or {}
            stored_id = (runtime.get("webex_webhook") or legacy.get("webex_webhook") or {}).get(
                "id"
            )
            if stored_id != webhook_id:
                continue

            workflow_id = wf.get("id")
            if not workflow_id:
                continue

            runtime.deactivate(workflow_id)
            db.workflow.clear_fuse_runtime_webex_webhook(workflow_id, owner_id)
            if wf.get("status") == "active":
                db.workflow.update_status(workflow_id, owner_id, "inactive")
            logger.info(
                "[Webex] Synced workflow %s after manual webhook %s removal",
                workflow_id,
                webhook_id,
            )

        cursor = page.get("next_cursor")
        if not cursor:
            break


def verify_webex_webhook_signature(body_bytes: bytes, signature: str, secret: str) -> bool:
    """Verify X-Spark-Signature (HMAC-SHA1 hex digest of the raw body)."""
    if not signature or not secret:
        return False
    digest = _hmac.new(secret.encode(), body_bytes, hashlib.sha1).hexdigest()
    return _hmac.compare_digest(signature, digest)


def fetch_webex_message(access_token: str, message_id: str) -> dict:
    """Fetch full message details from the Webex API."""
    response = requests.get(
        f"{CONFIG.WEBEX_API_BASE}/messages/{message_id}",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=30,
    )
    if response.status_code != 200:
        raise RuntimeError(f"Failed to fetch Webex message {message_id}: {response.text}")
    return response.json()


def get_webex_own_person_id(access_token: str) -> str | None:
    """Return the authenticated user's Webex person ID (for skipping own messages / mentions)."""
    try:
        response = requests.get(
            f"{CONFIG.WEBEX_API_BASE}/people/me",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=15,
        )
        if response.status_code == 200:
            return response.json().get("id")
    except Exception:
        logger.debug("Failed to fetch Webex /people/me", exc_info=True)
    return None


def fetch_webex_person(access_token: str, person_id: str) -> dict:
    """Fetch person details from the Webex API."""
    response = requests.get(
        f"{CONFIG.WEBEX_API_BASE}/people/{person_id}",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=30,
    )
    if response.status_code != 200:
        raise RuntimeError(f"Failed to fetch Webex person {person_id}: {response.text}")
    return response.json()


def send_webex_message(
    access_token: str,
    *,
    send_to: str,
    destination: str,
    message: str,
    use_markdown: bool = False,
) -> dict:
    """Send a Webex message to a room or person."""
    payload: dict = {}
    send_to = (send_to or "room").lower()

    if send_to == "room":
        payload["roomId"] = destination
    elif send_to == "person_email":
        payload["toPersonEmail"] = destination
    elif send_to == "person_id":
        payload["toPersonId"] = destination
    else:
        raise ValueError(f"Unknown send_to value: '{send_to}'")

    if use_markdown:
        payload["markdown"] = message
    else:
        payload["text"] = message

    response = requests.post(
        f"{CONFIG.WEBEX_API_BASE}/messages",
        headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
        json=payload,
        timeout=30,
    )
    if response.status_code not in (200, 201):
        raise RuntimeError(f"Webex send message failed: {response.text}")
    return response.json()


def normalise_webex_message_event(
    access_token: str,
    event_payload: dict,
    starter_config: dict,
    *,
    own_person_id: str | None = None,
) -> dict | None:
    """
    Convert a Webex webhook event into workflow trigger_data.

    Returns None when the message should be ignored (filters).
    """
    data = event_payload.get("data") or {}
    message_id = data.get("id")
    if not message_id:
        return None

    include_body = bool(starter_config.get("include_message_body"))
    mentions_only = bool(starter_config.get("mentions_only"))

    person_id = data.get("personId") or event_payload.get("actorId")

    # Webex webhook payloads only carry IDs — fetch the full message when the
    # body is needed, when mention filtering requires content, or when we need
    # the sender ID to skip the connected account's own messages.
    message: dict | None = None
    if include_body or mentions_only or not person_id:
        message = fetch_webex_message(access_token, message_id)
        person_id = person_id or (message or {}).get("personId")

    if own_person_id and person_id == own_person_id:
        return None

    if mentions_only and message:
        mentioned = message.get("mentionedPeople") or []
        if own_person_id and own_person_id not in mentioned:
            return None
        if not own_person_id and not mentioned:
            return None

    text = ""
    if include_body and message:
        text = message.get("text") or message.get("markdown") or ""

    return {
        "message_id": message_id,
        "text": text,
        "person_id": person_id,
        "person_email": (message or {}).get("personEmail") or data.get("personEmail"),
        "room_id": (message or {}).get("roomId") or data.get("roomId"),
        "room_type": (message or {}).get("roomType"),
        "created": (message or {}).get("created") or data.get("created"),
        "is_mention": bool((message or {}).get("mentionedPeople")) if message else False,
        "triggered_at": datetime.utcnow().isoformat() + "Z",
    }