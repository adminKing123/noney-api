import requests
from datetime import datetime, timedelta
from db import db
from config import CONFIG

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
