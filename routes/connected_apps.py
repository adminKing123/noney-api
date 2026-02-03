from flask import Blueprint, request, jsonify
from middleware.auth import require_auth
from db import db

connected_apps_bp = Blueprint("connected_apps", __name__)

@connected_apps_bp.route("/connected-apps", methods=["GET"])
@require_auth
def get_connected_apps():
    """Get all connected apps for the authenticated user"""
    try:
        user_id = request.user.get("uid")
        connected_apps = db.connected_apps.get_user_connected_apps(user_id)
        return jsonify({"connected_apps": connected_apps or {}}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@connected_apps_bp.route("/connected-apps/<app_id>", methods=["POST"])
@require_auth
def connect_app(app_id):
    """Connect an app for the authenticated user"""
    try:
        user_id = request.user.get("uid")
        data = request.json
        provider = data.get("provider")
        scopes = data.get("scopes", [])
        
        if not provider:
            return jsonify({"error": "Provider is required"}), 400
        
        app_data = {
            "provider": provider,
            "scopes": scopes,
            "isConnected": True,
            "connectedAt": data.get("connectedAt"),
            "lastSync": data.get("lastSync"),
        }
        
        db.connected_apps.set_app_connected(user_id, app_id, app_data)
        
        return jsonify({
            "message": f"App {app_id} connected successfully",
            "app_data": app_data
        }), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@connected_apps_bp.route("/connected-apps/<app_id>", methods=["DELETE"])
@require_auth
def disconnect_app(app_id):
    """Disconnect an app for the authenticated user"""
    try:
        user_id = request.user.get("uid")
        db.connected_apps.set_app_disconnected(user_id, app_id)
        
        return jsonify({
            "message": f"App {app_id} disconnected successfully"
        }), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@connected_apps_bp.route("/connected-apps/<app_id>", methods=["PATCH"])
@require_auth
def update_app(app_id):
    """Update app data (e.g., last sync time)"""
    try:
        user_id = request.user.get("uid")
        data = request.json
        
        db.connected_apps.update_app_data(user_id, app_id, data)
        
        return jsonify({
            "message": f"App {app_id} updated successfully"
        }), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@connected_apps_bp.route("/connected-apps/verify/<app_id>", methods=["GET"])
@require_auth
def verify_app_connection(app_id):
    """Verify if an app is actually connected via Firebase"""
    try:
        user_id = request.user.get("uid")
        # Get user's connected apps from database
        connected_apps = db.connected_apps.get_user_connected_apps(user_id)
        
        if not connected_apps or app_id not in connected_apps:
            return jsonify({
                "isConnected": False,
                "message": "App not found in user's connections"
            }), 200
        
        app_data = connected_apps[app_id]
        
        # TODO: Verify with Firebase Admin SDK that the provider is actually linked
        # For now, we trust the database
        
        return jsonify({
            "isConnected": app_data.get("isConnected", False),
            "provider": app_data.get("provider"),
            "connectedAt": app_data.get("connectedAt"),
            "lastSync": app_data.get("lastSync"),
        }), 200
        
    except Exception as e:
        return jsonify({"error": str(e)}), 500
