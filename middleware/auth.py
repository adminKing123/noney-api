from functools import wraps
from db import db
from flask import request, jsonify

def require_auth(f):
    @wraps(f)  # ← CRITICAL: without this, multiple protected routes will conflict
    def wrapper(*args, **kwargs):
        auth_header = request.headers.get("Authorization", None)
        if not auth_header:
            return jsonify({"error": "Missing Authorization header"}), 401

        try:
            token = auth_header.split(" ")[1]
            request.user = db.user.authenticate(token)
        except Exception as e:
            return jsonify({"error": "Invalid or expired token"}), 401

        return f(*args, **kwargs)
    return wrapper