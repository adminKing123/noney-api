import urllib.parse
from datetime import datetime, timedelta

from flask import Blueprint, request, jsonify, redirect
from middleware.auth import require_auth
from db import db
from config import CONFIG
from utils.integrations.gmail_utils import refresh_gmail_access_token_if_expired
import requests # Keep requests here for gmail_oauth_callback and people API

bp = Blueprint("fuse_integrations", __name__)

# ─── Integrations ─────────────────────────────────────────────────────────────

INTEGRATION_NODES = [
    {
        "id": "gmail",
        "name": "Gmail Connect",
        "description": "Connect your Gmail account to send and receive emails.",
        "icon": "SiGmail",
        "configured": False
    },
    {
        "id": "webex",
        "name": "Webex Connect",
        "description": "Connect your Webex account to send messages and notifications.",
        "icon": "SiWebex",
        "configured": False
    }
]

@bp.route("/integration", methods=["GET"])
@require_auth
def get_integrations():
    """GET /fuse/integration — returns list of integration nodes and their config status."""
    user_id = request.user["uid"]
    
    # Fetch all of a user's configured integrations in one query
    user_integrations = db.integration.get_all_integrations(user_id)
    
    # Update the `configured` flag on the base INTEGRATION_NODES list
    response_nodes = []
    for node in INTEGRATION_NODES:
        node_id = node["id"]
        is_configured = False
        if node_id in user_integrations:
            # Integration is configured if the document exists and has a truthy
            # 'configured' flag.
            if user_integrations[node_id].get("configured"):
                is_configured = True
        
        # Create a copy to avoid modifying the global INTEGRATION_NODES list
        updated_node = {**node, "configured": is_configured}
        response_nodes.append(updated_node)
        
    return jsonify(response_nodes)

# ─── Gmail OAuth ──────────────────────────────────────────────────────────────

@bp.route("/integration/gmail/auth", methods=["GET"])
@require_auth
def gmail_oauth_start():
    """GET /fuse/integration/gmail/auth — starts the Google OAuth flow."""
    user_id = request.user["uid"]
    
    client_id = CONFIG.GOOGLE_OAUTH_CLIENT_ID
    redirect_uri = CONFIG.GOOGLE_OAUTH_REDIRECT_URI
    
    if not client_id or not redirect_uri:
        return jsonify({"error": "Google OAuth is not configured on the server."}), 503
        
    scopes = [
        "https://www.googleapis.com/auth/gmail.send",
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/userinfo.profile"
    ]
    
    auth_url = "https://accounts.google.com/o/oauth2/v2/auth"
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(scopes),
        "access_type": "offline",
        "prompt": "consent",
        "state": user_id  # Pass user_id to retrieve it in the callback
    }
    
    url = f"{auth_url}?{urllib.parse.urlencode(params)}"
    return jsonify({"auth_url": url})


@bp.route("/integration/gmail/callback", methods=["GET"])
def gmail_oauth_callback():
    """GET /fuse/integration/gmail/callback — handles Google OAuth redirect."""
    error = request.args.get("error")
    if error:
        return f"OAuth Error: {error}", 400
        
    code = request.args.get("code")
    user_id = request.args.get("state")  # We passed user_id in the state param
    
    if not code or not user_id:
        return "Missing code or state parameter", 400
        
    token_url = "https://oauth2.googleapis.com/token"
    data = {
        "code": code,
        "client_id": CONFIG.GOOGLE_OAUTH_CLIENT_ID,
        "client_secret": CONFIG.GOOGLE_OAUTH_CLIENT_SECRET,
        "redirect_uri": CONFIG.GOOGLE_OAUTH_REDIRECT_URI,
        "grant_type": "authorization_code"
    }
    
    response = requests.post(token_url, data=data)
    if response.status_code != 200:
        return f"Failed to get tokens: {response.text}", 400
        
    token_data = response.json()
    
    # Calculate expiry time
    expires_in = token_data.get("expires_in", 3600)
    expires_at = (datetime.utcnow() + timedelta(seconds=expires_in)).isoformat() + "Z"
    
    tokens = {
        "access_token": token_data.get("access_token"),
        "refresh_token": token_data.get("refresh_token"),
        "expires_at": expires_at
    }
    
    # Save tokens to database
    db.integration.save_integration_tokens(user_id, "gmail", tokens)
        
    return redirect(f"{CONFIG.FRONTEND_URL}/fuse/integrations")


@bp.route("/integration/gmail/info", methods=["GET"])
@require_auth
def gmail_integration_info():
    """GET /fuse/integration/gmail/info — returns Gmail integration details."""
    user_id = request.user["uid"]
    integration = db.integration.get_integration(user_id, "gmail")
    if not integration or not integration.get("configured"):
        return jsonify({"error": "Gmail integration not found or not configured."}), 404

    integration = refresh_gmail_access_token_if_expired(user_id, integration)
    if not integration:
        return jsonify({"error": "Failed to refresh Gmail access token. Please re-configure."}), 500

    access_token = integration.get("access_token")
    if not access_token:
        return jsonify({"error": "Gmail access token not available."}), 500

    # Fetch user's email from Google People API
    user_info_url = "https://www.googleapis.com/oauth2/v2/userinfo"
    headers = {"Authorization": f"Bearer {access_token}"}
    try:
        user_info_response = requests.get(user_info_url, headers=headers)
        user_info_response.raise_for_status() # Raise an exception for HTTP errors
        user_info = user_info_response.json()
        integration["email"] = user_info.get("email")
        integration["name"] = user_info.get("name")
    except requests.exceptions.RequestException as e:
        print(f"Error fetching Gmail user info: {e}")
        # Optionally handle token expiration specifically if the error indicates it
        return jsonify({"error": f"Failed to retrieve Gmail user info: {str(e)}"}), 500

    return jsonify(integration)


@bp.route("/integration/<integration_id>", methods=["DELETE"])
@require_auth
def revoke_integration(integration_id):
    """DELETE /fuse/integration/<id> — revokes an integration."""
    user_id = request.user["uid"]
    
    # Actually delete from db
    success = db.integration.delete_integration(user_id, integration_id)
    if not success:
        return jsonify({"error": "Integration not found or already removed"}), 404
        
    # If it's a google oauth integration, you could optionally call google's revoke endpoint here
    # requests.post("https://oauth2.googleapis.com/revoke", params={"token": token})
    
    return jsonify({"success": True})
