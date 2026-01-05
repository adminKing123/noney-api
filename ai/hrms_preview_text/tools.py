from langchain.tools import tool, ToolRuntime
from .utils import find_user, get_today_log_status, get_emp_projects, get_emp_project_log, get_user_mail_setting, get_attendance, fetch_data_from_endpoint, login, logout, get_project_modules, get_project_activities, generate_csv

@tool
def find_user_tool(query: str) -> dict:
    """
    Find user(s) from locally cached HRMS user data.

    Search behavior:
    - Partial, case-insensitive match on name
    - Exact match on user_id
    - Exact match on employee_id

    Args:
        query (str): Name, user_id, or employee_id to search for.

    Returns:
        list[dict]:
            - Empty list if no users are found
            - List with one user dictionary if a single match is found
            - List of up to 5 user dictionaries if multiple matches are found

        Each user dictionary may include (but is not limited to):
        - user_id (str)
        - employee_id (str)
        - name (str)
        - username / email (str)
        - designation (str)
        - user_type (str)
        - team_lead (str)
        - firm_name (str)
        - org_name (str)
        - working_hour (str)
        - joining_date (str)
        - leaving_date (str | None)
        - leave balances (casual, emergency, comp off, etc.)
        - signed_array (str): Authentication token for further API calls

    Note:
        - If multiple users are returned, the caller or agent
          should ask the end user to clarify which user they mean
          before proceeding.
    """
    return find_user(query)

@tool
def get_today_log_status_tool(user_id: str, signed_array: str) -> dict:
    """
    Fetch today's attendance log sessions for a specific user.

    This tool returns all login/logout records for the current day.
    A user may have multiple sessions (e.g., re-login after logout).

    Each record includes:
    - attendance_id: Attendance record identifier
    - total_time: Total worked time in seconds (may repeat across sessions)
    - ip_address: IP address used during login
    - log_date: Date of the attendance log (MM/DD/YYYY)
    - login: Login time (HH:MM)
    - logout: Logout time (HH:MM or "00:00" if still logged in)

    Args:
        user_id (str): Unique identifier of the user.
        signed_array (str): Authentication token for the user.

    Returns:
        dict: A list of today's attendance session records.
    """
    return get_today_log_status(user_id=user_id, signed_array=signed_array)


@tool
def get_emp_projects_tool(user_id: str, signed_array: str) -> dict:
    """
    Fetch all projects assigned to a specific employee.

    This tool returns a list of projects mapped to the given user.
    Each project contains metadata such as its ID, name, type, and current status
    (Active / In-Active).

    Args:
        user_id (str): Unique identifier of the employee whose projects are requested.
        signed_array (str): Authentication token used to authorize the request.

    Returns:
        dict: A response object containing a list of projects with the following fields:
            - project_id (str): Unique project identifier.
            - project_name (str): Human-readable project name.
            - project_type_id (str): Identifier representing the project category/type.
            - project_status (str): Current status of the project (e.g., "Active", "In-Active").
    """
    return get_emp_projects(user_id=user_id, signed_array=signed_array)


@tool
def get_emp_project_log_tool(
    user_id: str,
    signed_array: str,
    project_id: str = 0,
    start_date: str = "",
    end_date: str = ""
) -> dict:
    """
    Retrieve detailed work logs for an employee across one or more projects.

    This tool returns time-tracking and activity logs recorded by the employee.
    It supports filtering by project and date range and provides rich metadata
    including project, module, activity details, work descriptions, and hours logged.

    Filtering behavior:
    - If project_id is provided, logs are fetched only for that project.
    - If project_id is not provided or set to 0, logs from all projects are returned.
    - start_date and end_date can be used to limit logs to a specific date range.

    Args:
        user_id (str): Unique identifier of the employee.
        signed_array (str): Authentication token for request authorization.
        project_id (str, optional): Project identifier to filter logs.
            Use 0 or empty value to fetch logs for all projects.
        start_date (str, optional): Start date for filtering logs (YYYY-MM-DD).
        end_date (str, optional): End date for filtering logs (YYYY-MM-DD).

    Returns:
        dict: A response object containing a list of work log entries.
            Each log entry includes:
            - id (str): Unique identifier of the work log entry.
            - user_id (str): Identifier of the employee.
            - user_name (str): Name of the employee.
            - project_id (str): Project identifier.
            - project_name (str): Project name.
            - module_id (str): Module identifier.
            - module_name (str): Module name.
            - activity_id (str): Activity identifier.
            - activity_name (str): Activity name.
            - work_desc (str): Detailed description of work performed.
            - log_date (str): Date when the work was logged (MM/DD/YYYY).
            - hour_clocked (str): Number of hours logged for the entry.
    """
    return get_emp_project_log(
        user_id=user_id,
        project_id=project_id,
        signed_array=signed_array,
        start_date=start_date,
        end_date=end_date
    )


@tool
def get_user_mail_setting_tool(user_id: str, signed_array: str) -> dict:
    """
    Retrieve email notification preferences for a specific user.

    This tool returns the user's mail settings that control which
    system-generated emails and notifications are enabled or disabled.
    All preference values are returned as string booleans ("true" / "false").

    Args:
        user_id (str): Unique identifier of the user.
        signed_array (str): Authentication token used to authorize the request.

    Returns:
        dict: An object representing the user's email notification settings,
        containing the following fields:
            - mail_setting_id (str): Unique identifier for the mail settings record.
            - user_id (str): Identifier of the user.
            - daily_worklog (str): Whether daily work log email notifications are enabled.
            - daily_attendlog (str): Whether daily attendance email notifications are enabled.
            - apply_leave_mail (str): Email notification for leave application submission.
            - approve_leave_mail (str): Email notification when a leave request is approved.
            - passed_leave_action_mail (str): Email notification for processed leave actions.
            - reject_leave_mail (str): Email notification when a leave request is rejected.
            - emp_leave_req_mail (str): Email notification when an employee requests leave.
            - apply_compoff (str): Email notification for compensatory off applications.
            - compoff_action_mail (str): Email notification for comp-off approval/rejection actions.
    """
    return get_user_mail_setting(user_id=user_id, signed_array=signed_array)

@tool
def get_attendance_tool(
    user_id: str,
    signed_array: str,
    start_date: str = "",
    end_date: str = ""
) -> dict:
    """
    Retrieve attendance records for a user within an optional date range.

    This tool returns daily attendance details including logged working hours,
    late arrival status, override comments, and out-of-office information.
    Results can be filtered by a start and/or end date.

    Filtering behavior:
    - If no dates are provided, all available attendance records are returned.
    - If start_date is provided, records from that date onward are returned.
    - If end_date is provided, records up to that date are returned.
    - If both dates are provided, records within the range are returned.

    Args:
        user_id (str): Unique identifier of the user.
        signed_array (str): Authentication token for request authorization.
        start_date (str, optional): Start date filter (YYYY-MM-DD).
        end_date (str, optional): End date filter (YYYY-MM-DD).

    Returns:
        dict: A list of attendance entries where each entry contains:
            - attendance_id (str): Unique identifier of the attendance record.
            - user_id (str): Identifier of the user.
            - name (str): Full name of the user.
            - log_date (str): Date of attendance record (MM/DD/YYYY).
            - logged_hours (str): Total hours logged for the day (HH:MM).
            - is_came_late (str): Indicates late arrival status ("Yes" or "-").
            - user_override_comment (str | null): Manual comment added by the user, if any.
            - out_office_log (str | null): Out-of-office details, if applicable.
    """
    return get_attendance(
        user_id=user_id,
        signed_array=signed_array,
        start_date=start_date,
        end_date=end_date
    )

@tool
def fetch_data_tool(endpoint: str, user_id=None, signed_array=None) -> dict:
    """
    Call a raw HRMS API endpoint with a standard authenticated payload.

    This is a generic utility tool for fetching data from
    custom or unsupported API endpoints.

    Args:
        endpoint (str): API endpoint path (e.g. "/attendance/show_attendance").
        user_id (str, optional): User identifier override.
        signed_array (str, optional): Authentication token override.
    """
    return fetch_data_from_endpoint(
        endpoint,
        user_id=user_id,
        signed_array=signed_array
    )

@tool
def login_tool(
    user_id: str,
    signed_array: str,
    override_comment: str = ""
) -> dict:
    """
    Perform a login (check-in) action for a user in the HRMS system.

    Args:
        user_id (str): Unique identifier of the user.
        signed_array (str): Authentication token used to authorize the request.
        override_comment (str, optional): Optional comment attached to the login action.

    Returns:
        dict: A dictionary containing the result of the login action.
        - last_ms (str): Timestamp in milliseconds of the last action.
        - last_status (str): Status after the action ("login").
        - user_id (str): User identifier.
        - user_status (str | None): Additional user status, if any.
        - last_time (str): Human-readable time of the action.
        - message (str): Confirmation message (e.g., "You have checked in successfully.")
    """
    return login(
        user_id=user_id,
        signed_array=signed_array,
        override_comment=override_comment
    )

@tool
def logout_tool(
    user_id: str,
    signed_array: str,
    override_comment: str = ""
) -> dict:
    """
    Perform a logout (check-out) action for a user in the HRMS system.

    Args:
        user_id (str): Unique identifier of the user.
        signed_array (str): Authentication token used to authorize the request.
        override_comment (str, optional): Optional comment attached to the logout action.

    Returns:
        dict: A dictionary containing the result of the logout action.
        - last_ms (str): Timestamp in milliseconds of the last action.
        - last_status (str): Status after the action ("logout").
        - user_id (str): User identifier.
        - user_status (str | None): Additional user status, if any.
        - last_time (str): Human-readable time of the action.
        - message (str): Confirmation message (e.g., "You have checked out successfully.")
    """
    return logout(
        user_id=user_id,
        signed_array=signed_array,
        override_comment=override_comment
    )

@tool
def get_project_modules_tool(
    user_id: str,
    signed_array: str,
    project_id: str = None
) -> dict:
    """
    Retrieve modules associated with a specific project.

    Args:
        user_id (str): Unique identifier of the user.
        signed_array (str): Authentication token used to authorize the request.
        project_id (str, optional): Identifier of the project to fetch modules for.

    Returns:
        dict: List of modules linked to the specified project.

        Each module object contains:
            - project_id (str): Identifier of the project.
            - module_id (str): Unique identifier of the module.
            - module_name (str): Name of the module.
            - estimated_time (str): Estimated effort/time for the module (may be empty).
            - module_startdate (str): Module start date (DD/MM/YYYY).
            - module_enddate (str | None): Module end date, if available.
            - module_status (str): Current status of the module (e.g., Open).
    """
    return get_project_modules(
        user_id=user_id,
        signed_array=signed_array,
        project_id=project_id
    )


@tool
def get_project_activities_tool(
    user_id: str,
    signed_array: str,
    project_id: str = None
) -> dict:
    """
    Retrieve all activities associated with a specific project.

    This tool fetches project-level activity mappings for a given user.
    Each activity represents a task/category that can be logged under the project.

    Args:
        user_id (str): Unique identifier of the user.
        signed_array (str): Authentication token used to authorize the request.
        project_id (str, optional): Identifier of the project whose activities are required.

    Returns:
        dict: List of project activities.  
        Each item in the list contains:

        - project_id (str): Identifier of the project.
        - activity_id (str): Master activity identifier.
        - activity_name (str): Human-readable name of the activity.
        - total_forecast_hours (str): Forecasted hours allocated to this activity.
        - project_activity_id (str): Unique identifier mapping the activity to the project.
        - act_status (str): Activity status  
            - "1" → Active  
            - "0" → Inactive
    """
    return get_project_activities(
        user_id=user_id,
        signed_array=signed_array,
        project_id=project_id
    )

@tool
def get_csv_of_all_employees(runtime: ToolRuntime) -> dict:
    """
    Generate a CSV file containing details of all employees in the HRMS system.

    This tool fetches all employee records, generates a CSV file,
    uploads it, and returns metadata about the generated file
    including a public download URL.

    Args:
        runtime (ToolRuntime): Runtime context provided by LangChain.

    Returns:
        dict: Metadata of the generated CSV file with the following keys:
            - file_id (str): Unique identifier of the file
            - user_id (str): ID of the requesting user
            - original_name (str): Original filename
            - filename (str): Stored filename
            - file_type (str): Type of the file
            - size (int): File size in bytes
            - download_url (str): Public URL to download the CSV

    render as [All Employees.csv]({download_url})
    """
    return generate_csv(
        find_user("", None),
        runtime.context.get("user_id"),
        runtime.context.get("chat_uid")
    )

tools = [
    find_user_tool, 
    get_today_log_status_tool, 
    get_emp_projects_tool, 
    get_emp_project_log_tool, 
    get_user_mail_setting_tool, 
    get_attendance_tool, 
    fetch_data_tool,
    login_tool,
    logout_tool,
    get_project_modules_tool,
    get_project_activities_tool,
    get_csv_of_all_employees,
]