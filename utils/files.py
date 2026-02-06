import os
from github import Github
from werkzeug.utils import secure_filename
from config import CONFIG
import requests
from flask import Response, stream_with_context
from google import genai
from datetime import datetime
import mimetypes

github = Github(CONFIG.UPLOAD1.GITHUB_TOKEN)
repo = github.get_user().get_repo(CONFIG.UPLOAD1.GITHUB_REPO_NAME)

client = genai.Client()


def get_mime_type(filename):
    """
    Determine the appropriate MIME type for a file, with special handling for
    text-based files that Gemini can process.
    
    For unsupported file types, map them to text/plain so they can be processed as text.
    
    Args:
        filename: Name of the file
        
    Returns:
        MIME type string
    """
    # Supported Gemini file types
    SUPPORTED_IMAGE_TYPES = {
        '.png': 'image/png',
        '.jpg': 'image/jpeg',
        '.jpeg': 'image/jpeg',
        '.webp': 'image/webp',
        '.heic': 'image/heic',
        '.heif': 'image/heif',
    }
    
    SUPPORTED_VIDEO_TYPES = {
        '.mp4': 'video/mp4',
        '.mpeg': 'video/mpeg',
        '.mov': 'video/mov',
        '.avi': 'video/avi',
        '.flv': 'video/x-flv',
        '.mpg': 'video/mpg',
        '.webm': 'video/webm',
        '.wmv': 'video/wmv',
        '.3gpp': 'video/3gpp',
    }
    
    SUPPORTED_AUDIO_TYPES = {
        '.wav': 'audio/wav',
        '.mp3': 'audio/mp3',
        '.aiff': 'audio/aiff',
        '.aac': 'audio/aac',
        '.ogg': 'audio/ogg',
        '.flac': 'audio/flac',
    }
    
    TEXT_BASED_EXTENSIONS = {
        '.json', '.txt', '.md', '.csv', '.log', '.xml', '.yaml', '.yml',
        '.ini', '.conf', '.cfg', '.sql', '.py', '.js', '.ts', '.jsx', '.tsx',
        '.java', '.c', '.cpp', '.h', '.hpp', '.cs', '.rb', '.go', '.php',
        '.html', '.htm', '.css', '.scss', '.sass', '.less', '.sh', '.bash',
        '.env', '.gitignore', '.dockerignore', '.toml', '.properties',
        '.sqlite', '.sqlite3', '.db',
    }
    
    ext = os.path.splitext(filename)[1].lower()
    
    if ext in SUPPORTED_IMAGE_TYPES:
        return SUPPORTED_IMAGE_TYPES[ext]
    if ext in SUPPORTED_VIDEO_TYPES:
        return SUPPORTED_VIDEO_TYPES[ext]
    if ext in SUPPORTED_AUDIO_TYPES:
        return SUPPORTED_AUDIO_TYPES[ext]
    if ext == '.pdf':
        return 'application/pdf'
    
    if ext in TEXT_BASED_EXTENSIONS:
        return 'text/plain'
    
    guessed_type, _ = mimetypes.guess_type(filename)
    if guessed_type:
        if guessed_type.startswith('text/'):
            return 'text/plain'
        return guessed_type
    return 'text/plain'


def download_file_stream(github_path):
    """
    Stream a file download from GitHub raw URL
    
    Args:
        github_path: Path to file in GitHub repo
        
    Returns:
        Flask Response object with streaming file content
    """
    raw_url = (
        f"https://raw.githubusercontent.com/"
        f"{CONFIG.UPLOAD1.GITHUB_USERNAME}/"
        f"{CONFIG.UPLOAD1.GITHUB_REPO_NAME}/"
        f"{CONFIG.UPLOAD1.GITHUB_BRANCH_NAME}/"
        f"{github_path}"
    )

    filename = os.path.basename(github_path)

    r = requests.get(raw_url, stream=True)
    r.raise_for_status()

    return Response(
        stream_with_context(r.iter_content(chunk_size=8192)),
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Type": r.headers.get("Content-Type", "application/octet-stream")
        }
    )


def save_file(file, user_id, file_id, file_type=""):
    """
    Save a file to GitHub storage
    
    Args:
        file: Flask file object from request.files
        user_id: User ID for organizing files
        file_id: Unique file identifier
        file_type: Optional file type metadata
        
    Returns:
        Dictionary with file metadata
        
    Raises:
        Exception if upload fails
    """
    filename = secure_filename(f"{file_id}_{file.filename}")

    upload_dir = "uploads"
    os.makedirs(upload_dir, exist_ok=True)

    local_path = os.path.join(upload_dir, filename)

    github_path = f"{CONFIG.UPLOAD1.UPLOAD_FOLDER}/{user_id}/{filename}"
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

        # Determine appropriate mime type
        mime_type = get_mime_type(filename)
        
        # Upload to Gemini with explicit mime type
        genai_file = client.files.upload(
            file=local_path,
            config=dict(mime_type=mime_type)
        )

        if os.path.exists(local_path):
            os.remove(local_path)

        return {
            "file_id": file_id,
            "user_id": user_id,
            "original_name": file.filename,
            "filename": filename,
            "file_type": file_type,
            "size": len(file_content),
            "download_url": f"{CONFIG.HOST}/download/{github_path}",
            "genai_file": {
                "expiration_time": isinstance(genai_file.expiration_time, datetime) and genai_file.expiration_time.isoformat() or genai_file.expiration_time,
                "mime_type": genai_file.mime_type,
                "name": genai_file.name,
                "uri": genai_file.uri,
                "size_bytes": genai_file.size_bytes
            }
        }

    except Exception as e:
        if os.path.exists(local_path):
            os.remove(local_path)
        raise

def upload_file(file_path, content, commit_message):
    """
    Upload a file to GitHub repository
    
    Args:
        file_path: Path in GitHub repo
        content: File content as bytes
        commit_message: Git commit message
        
    Returns:
        True if successful, False otherwise
    """
    try:
        repo.create_file(
            path=file_path,
            message=commit_message,
            content=content,
            branch=CONFIG.UPLOAD1.GITHUB_BRANCH_NAME
        )
        return True
    except Exception as e:
        print(f"Error uploading file: {e}")
        return False

def remove_file(file_path, commit_message):
    """
    Remove a file from GitHub repository
    
    Args:
        file_path: Path to file in GitHub repo
        commit_message: Git commit message
        
    Returns:
        True if successful, False otherwise
    """
    try:
        contents = repo.get_contents(file_path, ref=CONFIG.UPLOAD1.GITHUB_BRANCH_NAME)
        repo.delete_file(
            path=file_path,
            message=commit_message,
            sha=contents.sha,
            branch=CONFIG.UPLOAD1.GITHUB_BRANCH_NAME
        )
        return True
    except Exception as e:
        print(f"Error removing file: {e}")
        return False
