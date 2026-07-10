import requests
import secrets
import hashlib
import hmac
from datetime import datetime, timedelta
from db import db
from config import CONFIG
import logging

logger = logging.getLogger(__name__)

def refresh_github_access_token_if_expired(user_id: str, integration: dict) -> dict | None:
    """Checks if the access token is expired and refreshes it if needed for Github."""
    expires_at_str = integration.get("expires_at")
    if not expires_at_str:
        return integration

    expires_at = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
    if datetime.utcnow().replace(tzinfo=None) < expires_at.replace(tzinfo=None):
        return integration

    refresh_token = integration.get("refresh_token")
    if not refresh_token:
        print("No refresh token available for Github integration.")
        return None

    token_url = "https://github.com/login/oauth/access_token"
    data = {
        "client_id": CONFIG.GITHUB_OAUTH_CLIENT_ID,
        "client_secret": CONFIG.GITHUB_OAUTH_CLIENT_SECRET,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }
    headers = {"Accept": "application/json"}
    response = requests.post(token_url, data=data, headers=headers)
    if response.status_code != 200:
        print(f"Failed to refresh Github token: {response.text}")
        return None

    token_data = response.json()
    if "error" in token_data:
        print(f"Failed to refresh Github token: {token_data}")
        return None

    new_expires_in = token_data.get("expires_in", 28800)
    new_expires_at = (datetime.utcnow() + timedelta(seconds=int(new_expires_in))).isoformat() + "Z"

    updated_tokens = {
        "access_token": token_data.get("access_token"),
        "refresh_token": token_data.get("refresh_token", refresh_token),
        "expires_at": new_expires_at,
    }
    db.integration.save_integration_tokens(user_id, "github", updated_tokens)
    print(
        f"[Github Refresh] Token refreshed for user {user_id}. "
        f"New expires_at: {new_expires_at}"
    )
    return {**integration, **updated_tokens}

def get_github_access_token(user_id: str, integration: dict | None = None) -> str | None:
    """Return a valid Github access token, refreshing if needed."""
    integration = integration or db.integration.get_integration(user_id, "github")
    if not integration:
        return None
    integration = refresh_github_access_token_if_expired(user_id, integration)
    if not integration:
        return None
    return integration.get("access_token")

def create_github_webhook(
    access_token: str,
    *,
    repo_name: str,
    target_url: str,
    secret: str | None = None,
    events: list[str] | None = None,
) -> dict:
    webhook_secret = secret or secrets.token_urlsafe(32)
    events = events or ["pull_request", "pull_request_review"]
    
    payload = {
        "name": "web",
        "active": True,
        "events": events,
        "config": {
            "url": target_url,
            "content_type": "json",
            "insecure_ssl": "0",
            "secret": webhook_secret
        }
    }
    
    response = requests.post(
        f"https://api.github.com/repos/{repo_name}/hooks",
        headers={"Authorization": f"Bearer {access_token}", "Accept": "application/vnd.github.v3+json"},
        json=payload,
        timeout=30,
    )
    
    if response.status_code not in (200, 201):
        raise RuntimeError(f"Failed to create Github webhook for {repo_name}: {response.text}")
        
    data = response.json()
    webhook_id = data.get("id")
    if not webhook_id:
        raise RuntimeError("Github webhook response missing id.")
        
    return {**data, "id": str(webhook_id), "secret": webhook_secret, "repo_name": repo_name}

def delete_github_webhook(access_token: str, repo_name: str, webhook_id: str) -> bool:
    if not webhook_id or not repo_name:
        return False
    response = requests.delete(
        f"https://api.github.com/repos/{repo_name}/hooks/{webhook_id}",
        headers={"Authorization": f"Bearer {access_token}", "Accept": "application/vnd.github.v3+json"},
        timeout=30,
    )
    if response.status_code in (200, 204, 404):
        return True
    logger.warning("Failed to delete Github webhook %s on %s: %s", webhook_id, repo_name, response.text)
    return False

def cleanup_github_workflow_webhook(owner_id: str, compiled_graph: dict | None) -> bool:
    if not compiled_graph:
        return False

    starter = compiled_graph.get("starter") or {}
    if starter.get("node_type") != "github_pull_request":
        return False

    webhook_meta = compiled_graph.get("github_webhook") or {}
    webhook_id = webhook_meta.get("id")
    repo_name = webhook_meta.get("repo_name")
    if not webhook_id or not repo_name:
        return False

    access_token = get_github_access_token(owner_id)
    if not access_token:
        logger.warning(
            "[Github] Cannot delete webhook %s — no access token for user %s",
            webhook_id,
            owner_id,
        )
        return False

    deleted = delete_github_webhook(access_token, repo_name, webhook_id)
    if deleted:
        logger.info("[Github] Removed webhook %s during workflow cleanup", webhook_id)
    return deleted

def list_all_github_webhooks(access_token: str, repo_name: str) -> list[dict]:
    if not repo_name:
        return []
    response = requests.get(
        f"https://api.github.com/repos/{repo_name}/hooks",
        headers={"Authorization": f"Bearer {access_token}", "Accept": "application/vnd.github.v3+json"},
        timeout=30,
    )
    if response.status_code != 200:
        logger.warning(f"Failed to list Github webhooks for {repo_name}: {response.text}")
        return []
    return response.json()

def serialize_github_webhook_for_ui(item: dict) -> dict:
    target_url = item.get("config", {}).get("url", "")
    return {
        "id": str(item.get("id")),
        "name": item.get("name"),
        "target_url": target_url,
        "events": item.get("events"),
        "active": item.get("active"),
        "created": item.get("created_at"),
        "is_fuse_managed": "/fuse/github/webhook/" in target_url,
    }

def sync_github_workflows_after_webhook_removal(owner_id: str, webhook_id: str) -> None:
    from fuse.runtime import runtime

    cursor: dict | None = None
    while True:
        kwargs: dict = {"limit": 100}
        if cursor:
            kwargs["after_created_at"] = cursor.get("after_created_at")
            kwargs["after_id"] = cursor.get("after_id")

        page = db.workflow.list_for_owner(owner_id, **kwargs)
        for wf in page.get("items") or []:
            compiled = wf.get("compiled_graph") or {}
            stored_id = str((compiled.get("github_webhook") or {}).get("id"))
            if stored_id != str(webhook_id):
                continue

            workflow_id = wf.get("id")
            if not workflow_id:
                continue

            runtime.deactivate(workflow_id)
            if "github_webhook" in compiled:
                compiled.pop("github_webhook")
                db.workflow.save_compilation(
                    workflow_id, owner_id, compiled, 
                    compiled.get("graph_hash"), compiled.get("compiled_at")
                )
            if wf.get("status") == "active":
                db.workflow.update_status(workflow_id, owner_id, "inactive")
            logger.info(
                "[Github] Synced workflow %s after manual webhook %s removal",
                workflow_id,
                webhook_id,
            )

        cursor = page.get("next_cursor")
        if not cursor:
            break

def verify_github_webhook_signature(body_bytes: bytes, signature: str, secret: str) -> bool:
    if not signature or not secret:
        return False
    digest = hmac.new(secret.encode(), body_bytes, hashlib.sha256).hexdigest()
    expected_signature = f"sha256={digest}"
    return hmac.compare_digest(signature, expected_signature)

def list_github_repos(access_token: str) -> list[dict]:
    response = requests.get(
        "https://api.github.com/user/repos?per_page=100",
        headers={"Authorization": f"Bearer {access_token}", "Accept": "application/vnd.github.v3+json"},
        timeout=30,
    )
    if response.status_code != 200:
        logger.warning(f"Failed to list Github repos: {response.text}")
        return []
    return response.json()

def list_github_branches(access_token: str, repo_name: str) -> list[dict]:
    if not repo_name:
        return []
    response = requests.get(
        f"https://api.github.com/repos/{repo_name}/branches?per_page=100",
        headers={"Authorization": f"Bearer {access_token}", "Accept": "application/vnd.github.v3+json"},
        timeout=30,
    )
    if response.status_code != 200:
        logger.warning(f"Failed to list Github branches for {repo_name}: {response.text}")
        return []
    return response.json()

def normalise_github_pr_event(
    event_payload: dict,
    event_type: str,
    starter_config: dict
) -> dict | None:
    action_type = starter_config.get("action_type", "all")
    branch_name = (starter_config.get("branch_name") or "").strip()
    
    event_action = event_payload.get("action", "")
    
    if event_type == "pull_request":
        pr = event_payload.get("pull_request", {})
        merged = pr.get("merged", False)
        target_branch = pr.get("base", {}).get("ref", "")
        
        if branch_name and target_branch != branch_name:
            return None
            
        if action_type != "all":
            if action_type == "opened" and event_action != "opened":
                return None
            if action_type == "synchronize" and event_action != "synchronize":
                return None
            if action_type == "merged" and not (event_action == "closed" and merged):
                return None
            if action_type == "closed_unmerged" and not (event_action == "closed" and not merged):
                return None
            if action_type == "review_submitted":
                return None
                
    elif event_type == "pull_request_review":
        pr = event_payload.get("pull_request", {})
        target_branch = pr.get("base", {}).get("ref", "")
        
        if branch_name and target_branch != branch_name:
            return None
            
        if action_type != "all" and action_type != "review_submitted":
            return None
            
        if event_action != "submitted":
            return None
    else:
        return None

    pr = event_payload.get("pull_request", {})
    return {
        "pr_id": pr.get("id"),
        "pr_number": pr.get("number"),
        "pr_title": pr.get("title"),
        "pr_description": pr.get("body") or "",
        "pr_url": pr.get("html_url"),
        "event_type": event_type,
        "event_action": event_action,
        "user_login": event_payload.get("sender", {}).get("login"),
        "repository_name": event_payload.get("repository", {}).get("full_name", ""),
        "source_branch": pr.get("head", {}).get("ref", ""),
        "target_branch": pr.get("base", {}).get("ref", ""),
        "pr_state": pr.get("state", ""),
        "merged": pr.get("merged", False),
        "additions": pr.get("additions", 0),
        "deletions": pr.get("deletions", 0),
        "changed_files": pr.get("changed_files", 0),
        "review_state": event_payload.get("review", {}).get("state", ""),
        "review_body": event_payload.get("review", {}).get("body", ""),
        "triggered_at": datetime.utcnow().isoformat() + "Z",
    }
