import base64
import json
import requests
from datetime import datetime
import re
from config import CONFIG
import pickle
import os

# ---------------- Configuration ---------------- #
HR_CODE = CONFIG.HRMS.HR_CODE
API_BASE = CONFIG.HRMS.API_BASE

# ---------------- Global Defaults ---------------- #
DEFAULT_USER_ID = CONFIG.HRMS.DEFAULT_USER_ID
DEFAULT_SIGNED_ARRAY = CONFIG.HRMS.DEFAULT_SIGNED_ARRAY

# ---------------- Load Users Data ---------------- #
USERS = None
users_data_path = os.path.join(os.path.dirname(__file__), "users.data")
with open(users_data_path, "rb") as f:
    USERS = pickle.load(f)

# ---------------- Utility Functions ---------------- #

def log_response(data, filename="response.log"):
    try:
        with open(filename, "r") as f:
            old_content = f.read()
    except FileNotFoundError:
        old_content = ""

    with open(filename, "w") as f:
        f.write(f"[{datetime.now().isoformat()}]\n")
        f.write(json.dumps(data, indent=2))
        f.write("\n" + "="*50 + "\n")
        f.write(old_content)

def atob(b64: str) -> str:
    """JS-like atob: decode a base64 string into a binary string (latin-1)."""
    raw = base64.b64decode(b64)
    return raw.decode('latin-1')

def btoa(binary_str: str) -> str:
    """JS-like btoa: encode a binary string (latin-1) into base64."""
    if not isinstance(binary_str, str):
        raise TypeError("btoa expects a str")
    raw = binary_str.encode('latin-1')
    return base64.b64encode(raw).decode('ascii')

def encode(data):
    """Encode a dict to base64 JSON payload."""
    return {"data": base64.b64encode(json.dumps(data).encode()).decode()}

def decode(res):
    """Decode base64 JSON response."""
    data = res["res"]
    return json.loads(base64.b64decode(data).decode())

def get_code(data):
    string = f'{data["user_id"]}|{data["employee_id"]}|{data["username"]}|{data["user_type"]}'
    return btoa(string)

# ---------------- Core Request Handler ---------------- #

def post_request(endpoint: str, payload: dict, log: bool = False):
    """Generic POST request handler with base64 encoding/decoding and logging."""
    encoded_payload = encode(payload)
    try:
        resp = requests.post(
            f"{API_BASE}{endpoint}",
            json=encoded_payload,
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        if resp.status_code == 200:
            data = decode(resp.json())
            if log:
                log_response(data)
            return data
        return {"error": f"Failed with status {resp.status_code}"}
    except requests.RequestException as e:
        return {"error": f"Request failed: {str(e)}"}

def build_user_payload(user_id=None, signed_array=None, extra_fields=None):
    """Build standard user payload with optional extra fields and defaults."""
    global DEFAULT_USER_ID, DEFAULT_SIGNED_ARRAY
    payload = {
        "hrcode": HR_CODE,
        "user_id": user_id or DEFAULT_USER_ID,
        "project_status": 1,
        "signed_array": signed_array or DEFAULT_SIGNED_ARRAY
    }
    if extra_fields:
        payload.update(extra_fields)
    return payload

# ---------------- API Functions ---------------- #

def fetch_data_from_endpoint(endpoint: str, user_id=None, signed_array=None):
    payload = build_user_payload(user_id, signed_array)
    return post_request(endpoint, payload)

def find_user_local(query: str) -> str:
    """
    Search user by:
    - name (partial, case-insensitive)
    - user_id (exact)
    - employee_id (exact)

    returns
    - user_id
    - employee_id
    - name
    - signed_array
    """
    q = str(query).strip().lower()

    for user in USERS:
        name = str(user.get("name", "")).lower()
        user_id = str(user.get("user_id", "")).lower()
        employee_id = str(user.get("employee_id", "")).lower()

        if (
            q == user_id or
            q == employee_id or
            q in name
        ):
            return user

    return None

def get_user_by_id(user_id=None, signed_array=None):
    endpoint = "/user/get_user_list"
    payload = build_user_payload(user_id, signed_array)
    data = post_request(endpoint, payload)

    if "response_data" in data:
        for user in data["response_data"]:
            if str(user.get("user_id")) == str(user_id or DEFAULT_USER_ID):
                return user
    return data

def get_today_log_status(user_id=None, signed_array=None):
    endpoint = "/attendance/total_logs_detail"
    payload = build_user_payload(user_id, signed_array)
    data = post_request(endpoint, payload)
    response_data = data.get("response_data", [])
    return response_data

def get_emp_projects(user_id=None, signed_array=None):
    endpoint = "/project/get_emp_projects"
    payload = build_user_payload(user_id, signed_array)
    data = post_request(endpoint, payload)
    return data.get("response_data", [])

def get_user_mail_setting(user_id=None, signed_array=None):
    endpoint = "/setting/get_user_mail_setting"
    payload = build_user_payload(user_id, signed_array)
    data = post_request(endpoint, payload)
    return data.get("response_data", [])

def get_attendance(start_date="", end_date="", user_id=None, signed_array=None):
    endpoint = "/attendance/show_attendance"
    extra_fields = {"start_date": start_date, "end_date": end_date}
    payload = build_user_payload(user_id, signed_array, extra_fields)
    data = post_request(endpoint, payload)
    return data.get("response_data", [])

def get_emp_project_log(start_date="", end_date="", user_id=None, signed_array=None, project_id=0):
    endpoint = "/project/get_emp_project_log"
    payload = {
        "hrcode": HR_CODE,
        "project_id": project_id,
        "emp_id": user_id or DEFAULT_USER_ID,
        "module_id": 0,
        "activity_id": 0,
        "start_date": start_date,
        "end_date": end_date,
        "groupby": "none",
        "sortby": "ASC",
        "signed_array": signed_array or DEFAULT_SIGNED_ARRAY
    }

    encoded = base64.b64encode(json.dumps(payload).encode()).decode()
    payload = {"data": encoded}

    try:
        resp = requests.post(
            f"{API_BASE}{endpoint}",
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=10
        )
        if resp.status_code == 200:
            data = decode(resp.json())
            return data.get("response_data", [])
        return {"error": f"Failed with status {resp.status_code}"}
    except requests.RequestException as e:
        return {"error": f"Request failed: {str(e)}"}

def login(user_id=None, signed_array=None, override_comment=""):
    endpoint = "/attendance/fill_attendance"
    payload = build_user_payload(user_id, signed_array)
    extra_fields = {"override_comment": override_comment}
    data = post_request(endpoint, payload, extra_fields)
    result = data.get("response_data", {})
    result["message"] = data.get("message", "")
    return result

def logout(user_id=None, signed_array=None, override_comment=""):
    endpoint = "/attendance/fill_attendance"
    payload = build_user_payload(user_id, signed_array)
    extra_fields = {"override_comment": override_comment}
    data = post_request(endpoint, payload, extra_fields)
    result = data.get("response_data", {})
    result["message"] = data.get("message", "")
    return result