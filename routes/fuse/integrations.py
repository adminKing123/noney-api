import urllib.parse
from datetime import datetime, timedelta

from flask import Blueprint, request, jsonify, redirect
from middleware.auth import require_auth
from db import db
from config import CONFIG
from utils.integrations.gmail_utils import refresh_gmail_access_token_if_expired
from utils.integrations.webex_utils import refresh_webex_access_token_if_expired
from utils.integrations.google_sheets_utils import refresh_google_sheets_access_token_if_expired
from utils.integrations.github_utils import refresh_github_access_token_if_expired
import requests # Keep requests here for OAuth callbacks and user info APIs

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
    },
    {
        "id": "google_sheets",
        "name": "Google Sheets Connect",
        "description": "Connect your Google account to read and write spreadsheets.",
        "icon": "SiGooglesheets",
        "configured": False
    },
    {
        "id": "github",
        "name": "GitHub Connect",
        "description": "Connect your GitHub account to manage repositories and issues.",
        "icon": "SiGithub",
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
    redirect_uri = CONFIG.GOOGLE_MAIL_OAUTH_REDIRECT_URI
    
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
        "redirect_uri": CONFIG.GOOGLE_MAIL_OAUTH_REDIRECT_URI,
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


# ─── Webex OAuth ──────────────────────────────────────────────────────────────

@bp.route("/integration/webex/auth", methods=["GET"])
@require_auth
def webex_oauth_start():
    """GET /fuse/integration/webex/auth — starts the Webex OAuth flow."""
    user_id = request.user["uid"]

    client_id = CONFIG.WEBEX_OAUTH_CLIENT_ID
    redirect_uri = CONFIG.WEBEX_OAUTH_REDIRECT_URI

    if not client_id or not redirect_uri:
        return jsonify({"error": "Webex OAuth is not configured on the server."}), 503

    scopes = [s for s in CONFIG.WEBEX_OAUTH_SCOPES.split() if s]
    if not scopes:
        return jsonify({"error": "Webex OAuth scopes are not configured on the server."}), 503

    auth_url = "https://webexapis.com/v1/authorize"
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(scopes),
        "state": user_id,
    }

    url = f"{auth_url}?{urllib.parse.urlencode(params)}"
    return jsonify({"auth_url": url})


@bp.route("/integration/webex/callback", methods=["GET"])
def webex_oauth_callback():
    """GET /fuse/integration/webex/callback — handles Webex OAuth redirect."""
    error = request.args.get("error")
    if error:
        return f"OAuth Error: {error}", 400

    code = request.args.get("code")
    user_id = request.args.get("state")

    if not code or not user_id:
        return "Missing code or state parameter", 400

    token_url = "https://webexapis.com/v1/access_token"
    data = {
        "code": code,
        "client_id": CONFIG.WEBEX_OAUTH_CLIENT_ID,
        "client_secret": CONFIG.WEBEX_OAUTH_CLIENT_SECRET,
        "redirect_uri": CONFIG.WEBEX_OAUTH_REDIRECT_URI,
        "grant_type": "authorization_code",
    }

    response = requests.post(token_url, data=data)
    if response.status_code != 200:
        return f"Failed to get tokens: {response.text}", 400

    token_data = response.json()

    expires_in = token_data.get("expires_in", 1209600)
    expires_at = (datetime.utcnow() + timedelta(seconds=expires_in)).isoformat() + "Z"

    tokens = {
        "access_token": token_data.get("access_token"),
        "refresh_token": token_data.get("refresh_token"),
        "expires_at": expires_at,
    }

    refresh_token_expires_in = token_data.get("refresh_token_expires_in")
    if refresh_token_expires_in:
        tokens["refresh_token_expires_at"] = (
            datetime.utcnow() + timedelta(seconds=refresh_token_expires_in)
        ).isoformat() + "Z"

    db.integration.save_integration_tokens(user_id, "webex", tokens)

    return redirect(f"{CONFIG.FRONTEND_URL}/fuse/integrations")


@bp.route("/integration/webex/info", methods=["GET"])
@require_auth
def webex_integration_info():
    """GET /fuse/integration/webex/info — returns Webex integration details."""
    user_id = request.user["uid"]
    integration = db.integration.get_integration(user_id, "webex")
    if not integration or not integration.get("configured"):
        return jsonify({"error": "Webex integration not found or not configured."}), 404

    integration = refresh_webex_access_token_if_expired(user_id, integration)
    if not integration:
        return jsonify({"error": "Failed to refresh Webex access token. Please re-configure."}), 500

    access_token = integration.get("access_token")
    if not access_token:
        return jsonify({"error": "Webex access token not available."}), 500

    user_info_url = f"{CONFIG.WEBEX_API_BASE}/people/me"
    headers = {"Authorization": f"Bearer {access_token}"}
    try:
        user_info_response = requests.get(user_info_url, headers=headers)
        user_info_response.raise_for_status()
        user_info = user_info_response.json()
        integration["name"] = user_info.get("displayName")
        emails = user_info.get("emails") or []
        if emails:
            integration["email"] = emails[0] if len(emails) == 1 else ", ".join(emails)
        integration["person_id"] = user_info.get("id")
    except requests.exceptions.RequestException as e:
        print(f"Error fetching Webex user info: {e}")
        return jsonify({"error": f"Failed to retrieve Webex user info: {str(e)}"}), 500

    return jsonify(integration)


@bp.route("/integration/webex/rooms", methods=["GET"])
@require_auth
def webex_list_rooms():
    """GET /fuse/integration/webex/rooms — list Webex spaces/rooms for the linked account."""
    user_id = request.user["uid"]
    integration = db.integration.get_integration(user_id, "webex")
    if not integration or not integration.get("configured"):
        return jsonify({"error": "Webex integration not found or not configured."}), 404

    integration = refresh_webex_access_token_if_expired(user_id, integration)
    if not integration:
        return jsonify({"error": "Failed to refresh Webex access token. Please re-configure."}), 500

    access_token = integration.get("access_token")
    if not access_token:
        return jsonify({"error": "Webex access token not available."}), 500

    from utils.integrations.webex_utils import list_all_rooms, serialize_room_for_ui

    try:
        raw_items = list_all_rooms(access_token)
        rooms = [serialize_room_for_ui(item) for item in raw_items if item.get("id")]
        rooms.sort(key=lambda r: (r.get("type") != "group", (r.get("title") or "").lower()))
        return jsonify({"rooms": rooms, "total": len(rooms)})
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 502


@bp.route("/integration/webex/people", methods=["GET"])
@require_auth
def webex_list_people():
    """GET /fuse/integration/webex/people — list Webex people for destination picker."""
    user_id = request.user["uid"]
    integration = db.integration.get_integration(user_id, "webex")
    if not integration or not integration.get("configured"):
        return jsonify({"error": "Webex integration not found or not configured."}), 404

    integration = refresh_webex_access_token_if_expired(user_id, integration)
    if not integration:
        return jsonify({"error": "Failed to refresh Webex access token. Please re-configure."}), 500

    access_token = integration.get("access_token")
    if not access_token:
        return jsonify({"error": "Webex access token not available."}), 500

    from utils.integrations.webex_utils import list_all_people, serialize_person_for_ui

    try:
        raw_items = list_all_people(access_token)
        people = []
        for item in raw_items:
            entry = serialize_person_for_ui(item)
            if entry:
                people.append(entry)
        people.sort(key=lambda p: (p.get("display_name") or "").lower())
        return jsonify({"people": people, "total": len(people)})
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 502


@bp.route("/integration/webex/webhooks", methods=["GET"])
@require_auth
def webex_list_webhooks():
    """GET /fuse/integration/webex/webhooks — list Webex webhooks for the linked account."""
    user_id = request.user["uid"]
    integration = db.integration.get_integration(user_id, "webex")
    if not integration or not integration.get("configured"):
        return jsonify({"error": "Webex integration not found or not configured."}), 404

    integration = refresh_webex_access_token_if_expired(user_id, integration)
    if not integration:
        return jsonify({"error": "Failed to refresh Webex access token. Please re-configure."}), 500

    access_token = integration.get("access_token")
    if not access_token:
        return jsonify({"error": "Webex access token not available."}), 500

    from utils.integrations.webex_utils import list_all_webhooks, serialize_webhook_for_ui

    try:
        raw_items = list_all_webhooks(access_token)
        webhooks = [serialize_webhook_for_ui(item) for item in raw_items]
        return jsonify({"webhooks": webhooks, "total": len(webhooks)})
    except RuntimeError as exc:
        return jsonify({"error": str(exc)}), 502


@bp.route("/integration/webex/webhooks/<webhook_id>", methods=["DELETE"])
@require_auth
def webex_delete_webhook(webhook_id):
    """DELETE /fuse/integration/webex/webhooks/:id — remove a Webex webhook."""
    user_id = request.user["uid"]
    integration = db.integration.get_integration(user_id, "webex")
    if not integration or not integration.get("configured"):
        return jsonify({"error": "Webex integration not found or not configured."}), 404

    integration = refresh_webex_access_token_if_expired(user_id, integration)
    if not integration:
        return jsonify({"error": "Failed to refresh Webex access token. Please re-configure."}), 500

    access_token = integration.get("access_token")
    if not access_token:
        return jsonify({"error": "Webex access token not available."}), 500

    from utils.integrations.webex_utils import (
        delete_webhook,
        sync_fuse_workflows_after_webhook_removal,
    )

    if not delete_webhook(access_token, webhook_id):
        return jsonify({"error": "Failed to delete Webex webhook."}), 502

    sync_fuse_workflows_after_webhook_removal(user_id, webhook_id)
    return jsonify({"success": True, "id": webhook_id})


# ─── Google Sheets OAuth ──────────────────────────────────────────────────────

@bp.route("/integration/google_sheets/auth", methods=["GET"])
@require_auth
def google_sheets_oauth_start():
    """GET /fuse/integration/google_sheets/auth — starts the Google Sheets OAuth flow."""
    user_id = request.user["uid"]

    client_id = CONFIG.GOOGLE_OAUTH_CLIENT_ID
    redirect_uri = CONFIG.GOOGLE_SHEETS_OAUTH_REDIRECT_URI

    print(f"Starting Google Sheets OAuth for user {user_id} with client_id {client_id} and redirect_uri {redirect_uri}")

    if not client_id or not redirect_uri:
        return jsonify({"error": "Google Sheets OAuth is not configured on the server."}), 503

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/userinfo.email",
        "https://www.googleapis.com/auth/userinfo.profile",
    ]

    auth_url = "https://accounts.google.com/o/oauth2/v2/auth"
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": " ".join(scopes),
        "access_type": "offline",
        "prompt": "consent",
        "state": user_id,
    }

    url = f"{auth_url}?{urllib.parse.urlencode(params)}"
    return jsonify({"auth_url": url})


@bp.route("/integration/google_sheets/callback", methods=["GET"])
def google_sheets_oauth_callback():
    """GET /fuse/integration/google_sheets/callback — handles Google OAuth redirect."""
    error = request.args.get("error")
    if error:
        return f"OAuth Error: {error}", 400

    code = request.args.get("code")
    user_id = request.args.get("state")

    if not code or not user_id:
        return "Missing code or state parameter", 400

    token_url = "https://oauth2.googleapis.com/token"

    data = {
        "code": code,
        "client_id": CONFIG.GOOGLE_OAUTH_CLIENT_ID,
        "client_secret": CONFIG.GOOGLE_OAUTH_CLIENT_SECRET,
        "redirect_uri": CONFIG.GOOGLE_SHEETS_OAUTH_REDIRECT_URI,
        "grant_type": "authorization_code",
    }

    response = requests.post(token_url, data=data)
    if response.status_code != 200:
        return f"Failed to get tokens: {response.text}", 400

    token_data = response.json()

    expires_in = token_data.get("expires_in", 3600)
    expires_at = (datetime.utcnow() + timedelta(seconds=expires_in)).isoformat() + "Z"

    tokens = {
        "access_token": token_data.get("access_token"),
        "refresh_token": token_data.get("refresh_token"),
        "expires_at": expires_at,
    }

    db.integration.save_integration_tokens(user_id, "google_sheets", tokens)

    return redirect(f"{CONFIG.FRONTEND_URL}/fuse/integrations")


@bp.route("/integration/google_sheets/info", methods=["GET"])
@require_auth
def google_sheets_integration_info():
    """GET /fuse/integration/google_sheets/info — returns Google Sheets integration details."""
    user_id = request.user["uid"]
    integration = db.integration.get_integration(user_id, "google_sheets")
    if not integration or not integration.get("configured"):
        return jsonify({"error": "Google Sheets integration not found or not configured."}), 404

    integration = refresh_google_sheets_access_token_if_expired(user_id, integration)
    if not integration:
        return jsonify({"error": "Failed to refresh Google Sheets access token. Please re-configure."}), 500

    access_token = integration.get("access_token")
    if not access_token:
        return jsonify({"error": "Google Sheets access token not available."}), 500

    user_info_url = "https://www.googleapis.com/oauth2/v2/userinfo"
    headers = {"Authorization": f"Bearer {access_token}"}
    try:
        user_info_response = requests.get(user_info_url, headers=headers)
        user_info_response.raise_for_status()
        user_info = user_info_response.json()
        integration["email"] = user_info.get("email")
        integration["name"] = user_info.get("name")
    except requests.exceptions.RequestException as e:
        print(f"Error fetching Google Sheets user info: {e}")
        return jsonify({"error": f"Failed to retrieve Google Sheets user info: {str(e)}"}), 500

    return jsonify(integration)


# ─── GitHub OAuth ─────────────────────────────────────────────────────────────

@bp.route("/integration/github/auth", methods=["GET"])
@require_auth
def github_oauth_start():
    """GET /fuse/integration/github/auth — starts the GitHub OAuth flow."""
    user_id = request.user["uid"]

    client_id = CONFIG.GITHUB_OAUTH_CLIENT_ID
    redirect_uri = CONFIG.GITHUB_OAUTH_REDIRECT_URI

    print(f"Starting GitHub OAuth for user {user_id} with client_id {client_id} and redirect_uri {redirect_uri}")

    if not client_id or not redirect_uri:
        return jsonify({"error": "GitHub OAuth is not configured on the server."}), 503

    scopes = [
        "repo",
        "user:email",
    ]

    auth_url = "https://github.com/login/oauth/authorize"
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": " ".join(scopes),
        "state": user_id,
    }

    url = f"{auth_url}?{urllib.parse.urlencode(params)}"
    return jsonify({"auth_url": url})


@bp.route("/integration/github/callback", methods=["GET"])
def github_oauth_callback():
    """GET /fuse/integration/github/callback — handles GitHub OAuth redirect."""
    error = request.args.get("error")
    if error:
        return f"OAuth Error: {error}", 400

    code = request.args.get("code")
    user_id = request.args.get("state")

    if not code or not user_id:
        return "Missing code or state parameter", 400

    token_url = "https://github.com/login/oauth/access_token"

    data = {
        "code": code,
        "client_id": CONFIG.GITHUB_OAUTH_CLIENT_ID,
        "client_secret": CONFIG.GITHUB_OAUTH_CLIENT_SECRET,
        "redirect_uri": CONFIG.GITHUB_OAUTH_REDIRECT_URI,
    }

    headers = {"Accept": "application/json"}

    response = requests.post(token_url, data=data, headers=headers)
    if response.status_code != 200:
        return f"Failed to get tokens: {response.text}", 400

    token_data = response.json()

    if "error" in token_data:
        return f"OAuth Error: {token_data}", 400

    expires_in = token_data.get("expires_in", 28800)  # GitHub tokens usually expire in 8 hours if fine-grained
    expires_at = (datetime.utcnow() + timedelta(seconds=int(expires_in))).isoformat() + "Z"

    tokens = {
        "access_token": token_data.get("access_token"),
        "refresh_token": token_data.get("refresh_token"),
        "expires_at": expires_at,
    }

    db.integration.save_integration_tokens(user_id, "github", tokens)

    return redirect(f"{CONFIG.FRONTEND_URL}/fuse/integrations")


@bp.route("/integration/github/info", methods=["GET"])
@require_auth
def github_integration_info():
    """GET /fuse/integration/github/info — returns GitHub integration details."""
    user_id = request.user["uid"]
    integration = db.integration.get_integration(user_id, "github")
    if not integration or not integration.get("configured"):
        return jsonify({"error": "GitHub integration not found or not configured."}), 404

    integration = refresh_github_access_token_if_expired(user_id, integration)
    if not integration:
        return jsonify({"error": "Failed to refresh GitHub access token. Please re-configure."}), 500

    access_token = integration.get("access_token")
    if not access_token:
        return jsonify({"error": "GitHub access token not available."}), 500

    user_info_url = "https://api.github.com/user"
    headers = {"Authorization": f"Bearer {access_token}"}
    try:
        user_info_response = requests.get(user_info_url, headers=headers)
        user_info_response.raise_for_status()
        user_info = user_info_response.json()
        
        email = user_info.get("email")
        if not email:
             email_response = requests.get("https://api.github.com/user/emails", headers=headers)
             if email_response.status_code == 200:
                 emails = email_response.json()
                 primary_email = next((e for e in emails if e.get("primary")), None)
                 if primary_email:
                     email = primary_email.get("email")

        integration["email"] = email
        integration["name"] = user_info.get("name") or user_info.get("login")
        integration["login"] = user_info.get("login")
    except requests.exceptions.RequestException as e:
        print(f"Error fetching GitHub user info: {e}")
        return jsonify({"error": f"Failed to retrieve GitHub user info: {str(e)}"}), 500

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
