import os
from github import Github
from werkzeug.utils import secure_filename
from config import CONFIG

github = Github(CONFIG.GITHUB_TOKEN)
repo = github.get_user().get_repo(CONFIG.GITHUB_REPO_NAME)


def save_file(file, user_id, file_id, file_type=""):
    filename = secure_filename(f"{file_id}_{file.filename}")

    upload_dir = CONFIG.UPLOADS.UPLOAD_FOLDER
    os.makedirs(upload_dir, exist_ok=True)

    local_path = os.path.join(upload_dir, filename)

    github_path = f"uploads/{user_id}/{filename}"
    commit_message = f"Upload file {filename} for user {user_id}"

    try:
        file.save(local_path)

        with open(local_path, "rb") as f:
            file_content = f.read()

        success = upload_file(
            file_path=github_path,
            content=file_content,
            commit_message=commit_message
        )

        if not success:
            raise Exception("GitHub upload failed")

        if os.path.exists(local_path):
            os.remove(local_path)

        return {
            "file_id": file_id,
            "user_id": user_id,
            "original_name": file.filename,
            "filename": filename,
            "file_type": file_type,
            "size": len(file_content),
            # "download_url": (
            #     f"https://raw.githubusercontent.com/"
            #     f"{CONFIG.GITHUB_USERNAME}/"
            #     f"{CONFIG.GITHUB_REPO_NAME}/"
            #     f"{CONFIG.GITHUB_BRANCH_NAME}/"
            #     f"{github_path}"
            # )
            "download_url": f"https://sourceapis.onrender.com/download/{github_path}"
        }

    except Exception as e:
        if os.path.exists(local_path):
            os.remove(local_path)
        raise


def upload_file(file_path, content, commit_message):
    try:
        repo.create_file(
            path=file_path,
            message=commit_message,
            content=content,
            branch=CONFIG.GITHUB_BRANCH_NAME
        )
        return True
    except Exception as e:
        return False


def remove_file(file_path, commit_message):
    try:
        contents = repo.get_contents(file_path, ref=CONFIG.GITHUB_BRANCH_NAME)
        repo.delete_file(
            path=file_path,
            message=commit_message,
            sha=contents.sha,
            branch=CONFIG.GITHUB_BRANCH_NAME
        )
        return True
    except Exception as e:
        return False
