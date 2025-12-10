from firebase_admin import auth
from flask import request, jsonify

def require_auth(f):
    def wrapper(*args, **kwargs):
        auth_header = request.headers.get("Authorization", None)
        if not auth_header:
            return jsonify({"error": "Missing Authorization header"}), 401

        try:
            token = auth_header.split(" ")[1]  # "Bearer <token>"
            decoded = auth.verify_id_token(token)
            request.user = decoded  # attach user info
        except Exception as e:
            return jsonify({"error": "Invalid or expired token"}), 401

        return f(*args, **kwargs)

    wrapper.__name__ = f.__name__
    return wrapper
