import base64
import json
import requests
from datetime import datetime
from config import CONFIG
import csv
import io
import uuid
from werkzeug.datastructures import FileStorage
from utils.files import save_file
from typing import Union, Dict
from datetime import datetime
from collections import defaultdict
from functools import lru_cache

HR_CODE = CONFIG.HRMS.HR_CODE
API_BASE = CONFIG.HRMS.API_BASE
DEFAULT_USER_ID = CONFIG.HRMS.DEFAULT_USER_ID
DEFAULT_SIGNED_ARRAY = CONFIG.HRMS.DEFAULT_SIGNED_ARRAY
DATE_FMT = "%m/%d/%Y"

def parse_date(date_str):
    return datetime.strptime(date_str, DATE_FMT).date() if date_str else None

@lru_cache(maxsize=128)
def resolve_user(query: str) -> Union[Dict, tuple]:
    """
    Resolve a user query to a single user or return an error.
    
    Returns:
        tuple: (user_dict, None) if successful
        tuple: (None, error_dict) if failed
    """
    users = find_user(query)
    if not users:
        return None, {"error": f"No user found matching query: {query}"}
    if len(users) > 1:
        return None, {"error": f"Multiple users found for '{query}'. Please be more specific.", "matches": [u.get("name") for u in users]}
    return users[0], None

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

def find_user(query: str, limit=5) -> str:
    q = str(query).strip().lower()
    users = []
    endpoint = "/user/get_users"
    payload = build_user_payload()
    data = post_request(endpoint, payload)
    for user in data.get("response_data", []):
        name = str(user.get("name", "")).lower()
        user_id = str(user.get("user_id", "")).lower()
        employee_id = str(user.get("employee_id", "")).lower()
        username = str(user.get("username", "")).lower()
        user["signed_array"] = get_code(user)

        if (
            q == user_id or
            q == employee_id or
            q in name or
            q in username
        ):
            if limit is not None and len(users) >= limit:
                break
            users.append(user)
    return users

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
    extra_fields = {"override_comment": override_comment}
    payload = build_user_payload(user_id, signed_array, extra_fields)
    data = post_request(endpoint, payload)
    result = data.get("response_data", {})
    result["message"] = data.get("message", "")
    return result

def logout(user_id=None, signed_array=None, override_comment=""):
    endpoint = "/attendance/fill_attendance"
    extra_fields = {"override_comment": override_comment}
    payload = build_user_payload(user_id, signed_array, extra_fields)
    data = post_request(endpoint, payload)
    result = data.get("response_data", {})
    result["message"] = data.get("message", "")
    return result

def get_project_modules(user_id=None, signed_array=None, project_id=None):
    endpoint = "/project/get_modules"
    extra_fields = {"project_id": project_id}
    payload = build_user_payload(user_id, signed_array, extra_fields)
    data = post_request(endpoint, payload)
    result = data.get("response_data", {})
    return result

def get_project_activities(user_id=None, signed_array=None, project_id=None):
    endpoint = "/project/get_activities"
    extra_fields = {"project_id": project_id}
    payload = build_user_payload(user_id, signed_array, extra_fields)
    data = post_request(endpoint, payload)
    result = data.get("response_data", {})
    return result

def generate_csv(data, user_id, chat_id) -> dict:
    if not data:
        raise ValueError("No employee data found 😡")

    headers = data[0].keys()

    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=headers)
    writer.writeheader()
    writer.writerows(data)

    csv_bytes = output.getvalue().encode("utf-8")
    output.close()

    file_id = str(uuid.uuid4())
    filename = f"all_employees_{chat_id}.csv"

    csv_file = FileStorage(
        stream=io.BytesIO(csv_bytes),
        filename=filename,
        content_type="text/csv"
    )

    return save_file(
        file=csv_file,
        user_id=user_id,
        file_id=file_id,
        file_type="csv"
    )

def get_employee_leaves(user_id=None, signed_array=None, start_date=None, end_date=None):
    endpoint = "/leavemanager/get_user_leave_record"
    payload = build_user_payload(user_id, signed_array)
    data = post_request(endpoint, payload)
    leaves = data.get("response_data", [])
    result = []
    start = parse_date(start_date)
    end = parse_date(end_date)
    for leave in leaves:
        applied_date = parse_date(leave.get("applied_date"))
        e_user_id = leave.get("user_id")
        if e_user_id != user_id:
            continue
        if not applied_date:
            continue
        if start and applied_date < start:
            continue
        if end and applied_date > end:
            continue
        result.append(leave)
    return result

def get_employee_leaves_policy(user_id=None, signed_array=None):
    endpoint = "/setting/get_policy_setting"
    payload = build_user_payload(user_id, signed_array)
    data = post_request(endpoint, payload)

    result = data.get("response_data", {})
    return result

def get_holiday_and_leave_calendar(user_id=None, signed_array=None, start_date=None, end_date=None):
    if not start_date or not end_date:
        raise ValueError("start_date and end_date are required")

    endpoint = "/leavemanager/get_holiday_leave_records"
    payload = build_user_payload(user_id, signed_array)
    data = post_request(endpoint, payload)

    records = data.get("response_data", [])

    start = parse_date(start_date)
    end = parse_date(end_date)

    holidays = []
    leaves_by_date = defaultdict(list)

    for record in records:
        record_date = parse_date(record.get("date"))
        if not record_date:
            continue
        if record_date < start or record_date > end:
            continue

        name = record.get("name", "")
        if name.startswith("Leave:") or name.startswith("Half Day Leave:"):
            leaves_by_date[record_date.strftime(DATE_FMT)].append(name)
        else:
            holidays.append({
                "name": name,
                "date": record_date.strftime(DATE_FMT)
            })

    return {
        "holidays": holidays,
        "leaves": dict(leaves_by_date),
    }

def get_webex_token(user_id=None, signed_array=None):
    endpoint = "/user/get_user_spark_id"
    payload = build_user_payload(user_id, signed_array)
    data = post_request(endpoint, payload)

    result = data.get("response_data", data)
    if data.get("status") == "Success":
        return {
            "token": result
        }
    return {
        "error": data.get("message", "Error in getting the token")
    }

def fill_work_log(project_id, module_id, activity_id, work_desc, hour_clocked, user_id=None, signed_array=None):
    endpoint = "/project/fill_daily_log"

    extra_fields = {
        "project_id1": project_id,
        "module_id1": module_id,
        "activity_id1": activity_id,
        "work_desc1": work_desc,
        "hour_clocked1": hour_clocked,
        "work_quantified11": "",
        "work_quantified21": "",
        "log_date1": "",
        "send_mail1": "false",
        "project_id2": 0,
        "module_id2": 0,
        "activity_id2": 0,
        "work_quantified12": "",
        "work_quantified22": "",
        "log_date2": "",
        "send_mail2": "false",
    }
    payload = build_user_payload(user_id, signed_array, extra_fields)
    data = post_request(endpoint, payload)

    result = data.get("response_data", data)
    if data.get("status") == "Success":
        return {
            "token": result
        }
    return {
        "error": data.get("message", "Error in getting the token")
    }
