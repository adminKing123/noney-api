from langchain.tools import tool
from .utils import find_user_local, get_today_log_status, get_emp_projects, get_emp_project_log, get_user_mail_setting, get_attendance, fetch_data_from_endpoint

@tool
def get_a_user(query: str) -> dict:
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
    return find_user_local(query)

@tool
def get_today_log_status_tool(user_id: str, signed_array: str) -> dict:
    """
    Get today's log status for a user by user_id.

    returns
    - isLoggedIn (bool)
    - login_time (str)
    - logout_time (str)
    """
    return get_today_log_status(user_id=user_id, signed_array=signed_array)

@tool
def get_emp_projects_tool(user_id: str, signed_array: str) -> dict:
    """
    Get employee projects by user_id.

    returns
    - List of projects
    """
    return get_emp_projects(user_id=user_id, signed_array=signed_array)

@tool
def get_emp_project_log_tool(user_id: str, signed_array: str, project_id: str = 0, start_date: str = "", end_date: str = "") -> dict:
    """
    Get employee project log by user_id and project_id.
    project_id is optional; if not provided, fetches logs for all projects.
    start_date and end_date are optional filters.

    returns
    - Project log details
    """
    return get_emp_project_log(user_id=user_id, project_id=project_id, signed_array=signed_array, start_date=start_date, end_date=end_date)

@tool
def get_user_mail_setting_tool(user_id: str, signed_array: str) -> dict:
    """
    Get user mail settings by user_id.

    returns
    - Mail settings details
    """
    return get_user_mail_setting(user_id=user_id, signed_array=signed_array)

@tool
def get_attendance_tool(user_id: str, signed_array: str, start_date: str = "", end_date: str = "") -> dict:
    """
    Get attendance details for a user by user_id and date.
    start_date and end_date are optional filters.

    returns
    - Attendance details
    """
    return get_attendance(user_id=user_id, signed_array=signed_array, start_date=start_date, end_date=end_date)

@tool
def fetch_data_tool(endpoint: str, user_id=None, signed_array=None) -> dict:
    """
    Fetch data from a given API endpoint with the provided payload.

    returns
    - Response data from the API
    """
    return fetch_data_from_endpoint(endpoint, user_id=user_id, signed_array=signed_array)