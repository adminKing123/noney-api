import os
from werkzeug.utils import secure_filename
from config import CONFIG

def save_file(file, user_id, chat_id):
    filename = secure_filename(file.filename)

    chat_dir = os.path.join(
        CONFIG.UPLOADS.UPLOAD_FOLDER,
        f"user_{user_id}",
        f"chat_{chat_id}"
    )
    os.makedirs(chat_dir, exist_ok=True)

    file_path = os.path.join(chat_dir, filename)
    file.save(file_path)

    return {
        "filename": filename,
        "path": file_path,
        "size": os.path.getsize(file_path),
        "chat_id": chat_id,
        "user_id": user_id
    }
