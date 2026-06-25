import requests
from datetime import datetime, timedelta
from db import db
from config import CONFIG

def refresh_gmail_access_token_if_expired(user_id: str, integration: dict) -> dict | None:
    """Checks if the access token is expired and refreshes it if needed for Gmail."""
    expires_at_str = integration.get("expires_at")
    if not expires_at_str:
        return integration

    expires_at = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
    if datetime.utcnow().replace(tzinfo=None) < expires_at.replace(tzinfo=None):
        return integration  # Token is still valid

    # Token is expired, try to refresh
    refresh_token = integration.get("refresh_token")
    if not refresh_token:
        print("No refresh token available for Gmail integration.")
        return None

    token_url = "https://oauth2.googleapis.com/token"
    data = {
        "client_id": CONFIG.GOOGLE_OAUTH_CLIENT_ID,
        "client_secret": CONFIG.GOOGLE_OAUTH_CLIENT_SECRET,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }
    response = requests.post(token_url, data=data)
    if response.status_code != 200:
        print(f"Failed to refresh token: {response.text}")
        return None

    token_data = response.json()
    new_expires_in = token_data.get("expires_in", 3600)
    new_expires_at = (datetime.utcnow() + timedelta(seconds=new_expires_in)).isoformat() + "Z"

    updated_tokens = {
        "access_token": token_data.get("access_token"),
        "refresh_token": token_data.get("refresh_token", refresh_token), # Preserve old refresh token if new one not provided
        "expires_at": new_expires_at,
    }
    db.integration.save_integration_tokens(user_id, "gmail", updated_tokens)
    print(f"[Gmail Refresh] Token refreshed for user {user_id}. New expires_at: {new_expires_at}")
    return {**integration, **updated_tokens}
