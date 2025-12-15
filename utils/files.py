import os
from werkzeug.utils import secure_filename
from config import CONFIG

def save_file(file, user_id, file_id):
    filename = secure_filename(file_id + "_" + file.filename)

    chat_dir = os.path.join(
        CONFIG.UPLOADS.UPLOAD_FOLDER,
    )
    os.makedirs(chat_dir, exist_ok=True)

    file_path = os.path.join(chat_dir, filename)
    file.save(file_path)

    return {
        "file_id": file_id,
        "user_id": user_id,
        "original_name": file.filename,
        "filename": filename,
        "download_url": f"/uploads/{filename}",
        "size": os.path.getsize(file_path),
    }
