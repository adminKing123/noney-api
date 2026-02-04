from flask import Blueprint, request, jsonify
from middleware.auth import require_auth
from db import db
from utils import files

files_bp = Blueprint('files', __name__)

@files_bp.route("/download/<path:file_path>")
def download_file(file_path):
    """
    Download a file from GitHub storage
    """
    return files.download_file_stream(file_path)

@files_bp.route("/upload_file", methods=["POST"])
@require_auth
def upload_file():
    """
    Upload a file to GitHub storage and save metadata to Firebase
    """
    user_id = request.user.get("user_id", None)
    chat_id = request.form.get("chat_id")
    file_id = request.form.get("file_id")
    file_type = request.form.get("file_type", "")

    if not chat_id or not user_id or not file_id:
        return jsonify({"error": "chat_id, user_id, and file_id are required"}), 400

    if "file" not in request.files:
        return jsonify({"error": "No file provided"}), 400

    file = request.files["file"]

    if file.filename == "":
        return jsonify({"error": "Empty filename"}), 400

    try:
        file_meta = files.save_file(file, user_id, file_id, file_type)
        db.file.add_file(user_id, file_meta, chat_id=chat_id)
        return jsonify(file_meta), 201
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@files_bp.route("/delete_file/<file_id>", methods=["DELETE"])
@require_auth
def delete_file(file_id):
    """
    Delete a file from GitHub storage and remove metadata from Firebase
    """
    user_id = request.user.get("user_id")

    if not user_id:
        return jsonify({"error": "Unauthorized"}), 401

    try:
        file_data = db.file.get_file(file_id)
        if not file_data or "meta_data" not in file_data or "filename" not in file_data["meta_data"]:
            return jsonify({"error": "File not found"}), 404
        
        filename = file_data["meta_data"]["filename"]

        # GitHub repo path (same as upload logic)
        from config import CONFIG
        github_path = f"{CONFIG.UPLOAD1.UPLOAD_FOLDER}/{user_id}/{filename}"
        commit_message = f"Delete file {filename} for user {user_id}"

        success = files.remove_file(
            file_path=github_path,
            commit_message=commit_message
        )

        if not success:
            return jsonify({"error": "File not found or delete failed"}), 404
        
        db.file.remove_file(file_id)

        return jsonify({
            "success": True,
            "message": "File deleted successfully"
        }), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500
