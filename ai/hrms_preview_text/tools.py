from langchain.tools import tool, ToolRuntime
from typing import Optional
from .utils import (
    find_user, 
    resolve_user,
    get_today_log_status, 
    get_emp_projects, 
    get_emp_project_log, 
    get_user_mail_setting, 
    get_attendance, 
    fetch_data_from_endpoint, 
    login, 
    logout, 
    get_project_modules, 
    get_project_activities, 
    generate_csv,
    get_employee_leaves,
    get_employee_leaves_policy,
    get_holiday_and_leave_calendar,
)
from .schemas import (
    FindUserInput,
    TodayLogStatusInput,
    EmpProjectsInput,
    EmpProjectLogInput,
    UserMailSettingInput,
    AttendanceInput,
    FetchDataInput,
    LoginInput,
    LogoutInput,
    ProjectModulesInput,
    ProjectActivitiesInput,
    EmpLeavesInput,
    FindUserLeavesPolicyInput,
    EmpHolidaysAndLeaveCalendarInput,
)

@tool(args_schema=FindUserInput)
def find_user_tool(query: str) -> dict:
    """
    Find user(s) from locally cached HRMS user data.

    Search behavior:
    - Partial, case-insensitive match on name
    - Exact match on user_id
    - Exact match on employee_id

    Args:
        query (str): Name, user_id, employee_id, or email to search for.

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

@tool(args_schema=TodayLogStatusInput)
def get_today_log_status_tool(query: str) -> dict:
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
        query (str): Name, user_id, or employee_id to identify the user.

    Returns:
        dict: A list of today's attendance session records.
    """
    user, error = resolve_user(query)
    if error:
        return error
    return get_today_log_status(user_id=user["user_id"], signed_array=user["signed_array"])


@tool(args_schema=EmpProjectsInput)
def get_emp_projects_tool(query: str) -> dict:
    """
    Fetch all projects assigned to a specific employee.

    This tool returns a list of projects mapped to the given user.
    Each project contains metadata such as its ID, name, type, and current status
    (Active / In-Active).

    Args:
        query (str): Name, user_id, or employee_id to identify the user.

    Returns:
        dict: A response object containing a list of projects with the following fields:
            - project_id (str): Unique project identifier.
            - project_name (str): Human-readable project name.
            - project_type_id (str): Identifier representing the project category/type.
            - project_status (str): Current status of the project (e.g., "Active", "In-Active").
    """
    user, error = resolve_user(query)
    if error:
        return error
    return get_emp_projects(user_id=user["user_id"], signed_array=user["signed_array"])


@tool(args_schema=EmpProjectLogInput)
def get_emp_project_log_tool(
    query: str,
    project_id: str = "0",
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
        query (str): Name, user_id, or employee_id to identify the user.
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
    user, error = resolve_user(query)
    if error:
        return error
    return get_emp_project_log(
        user_id=user["user_id"],
        project_id=project_id,
        signed_array=user["signed_array"],
        start_date=start_date,
        end_date=end_date
    )


@tool(args_schema=UserMailSettingInput)
def get_user_mail_setting_tool(query: str) -> dict:
    """
    Retrieve email notification preferences for a specific user.

    This tool returns the user's mail settings that control which
    system-generated emails and notifications are enabled or disabled.
    All preference values are returned as string booleans ("true" / "false").

    Args:
        query (str): Name, user_id, or employee_id to identify the user.

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
    user, error = resolve_user(query)
    if error:
        return error
    return get_user_mail_setting(user_id=user["user_id"], signed_array=user["signed_array"])

@tool(args_schema=AttendanceInput)
def get_attendance_tool(
    query: str,
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
        query (str): Name, user_id, or employee_id to identify the user.
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
    user, error = resolve_user(query)
    if error:
        return error
    return get_attendance(
        user_id=user["user_id"],
        signed_array=user["signed_array"],
        start_date=start_date,
        end_date=end_date
    )

@tool(args_schema=FetchDataInput)
def fetch_data_tool(endpoint: str, user_id: Optional[str] = None, signed_array: Optional[str] = None) -> dict:
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

@tool(args_schema=LoginInput)
def login_tool(
    query: str,
    override_comment: str = ""
) -> dict:
    """
    Perform a login (check-in) action for a user in the HRMS system.

    Args:
        query (str): Name, user_id, or employee_id to identify the user.
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
    user, error = resolve_user(query)
    if error:
        return error
    return login(
        user_id=user["user_id"],
        signed_array=user["signed_array"],
        override_comment=override_comment
    )

@tool(args_schema=LogoutInput)
def logout_tool(
    query: str,
    override_comment: str = ""
) -> dict:
    """
    Perform a logout (check-out) action for a user in the HRMS system.

    Args:
        query (str): Name, user_id, or employee_id to identify the user.
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
    user, error = resolve_user(query)
    if error:
        return error
    return logout(
        user_id=user["user_id"],
        signed_array=user["signed_array"],
        override_comment=override_comment
    )

@tool(args_schema=ProjectModulesInput)
def get_project_modules_tool(
    query: str,
    project_id: Optional[str] = None
) -> dict:
    """
    Retrieve modules associated with a specific project.

    Args:
        query (str): Name, user_id, or employee_id to identify the user.
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
    user, error = resolve_user(query)
    if error:
        return error
    return get_project_modules(
        user_id=user["user_id"],
        signed_array=user["signed_array"],
        project_id=project_id
    )


@tool(args_schema=ProjectActivitiesInput)
def get_project_activities_tool(
    query: str,
    project_id: Optional[str] = None
) -> dict:
    """
    Retrieve all activities associated with a specific project.

    This tool fetches project-level activity mappings for a given user.
    Each activity represents a task/category that can be logged under the project.

    Args:
        query (str): Name, user_id, or employee_id to identify the user.
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
    user, error = resolve_user(query)
    if error:
        return error
    return get_project_activities(
        user_id=user["user_id"],
        signed_array=user["signed_array"],
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

@tool(args_schema=EmpLeavesInput)
def get_employee_leaves_tool(
    query: str,
    start_date: str = "",
    end_date: str = ""
) -> dict:
    """
    Retrieve leave applications for a specific employee within an optional date range.

    Args:
        query (str): Name, user_id, or employee_id to identify the employee.
        start_date (str, optional): Start date filter in MM/DD/YYYY format.
        end_date (str, optional): End date filter in MM/DD/YYYY format.

    Returns:
        dict: A list of leave application records.

        Each leave record contains:
            - app_id (str): Unique identifier of the leave application.
            - user_id (str): Identifier of the employee.
            - name (str): Full name of the employee.
            - email_id (str): Employee email address.
            - team_lead_id (str): Identifier of the reporting manager.
            - rm_name (str): Name of the reporting manager.
            - leave_type (str): Type of leave (e.g., "eml", "cal", "compoff").
            - applied_date (str): Date when the leave was applied (MM/DD/YYYY).
            - leave_sbj (str): Subject/title of the leave request.
            - leave_status (str): Current status of the leave
            - start_date (str): Leave start date (MM/DD/YYYY).
            - end_date (str): Leave end date (MM/DD/YYYY).
            - leave_days (str): Total number of leave days applied.
            - leave_desc (str): Detailed reason/description for the leave.
            - exl_used (str | None): Extra leave used, if applicable.
            - cal_used (str | None): Casual leave used, if applicable.
            - eml_used (str | None): Emergency leave used, if applicable.
            - transfer_deduction_rate (str | None): Leave transfer or deduction rate, if any.
            - is_halfleave_applied (str): Indicates if half-day leave was applied ("Yes"/"No").
            - halfleave_date1 (str | None): First half-day leave date, if applicable.
            - halfleave_date2 (str | None): Second half-day leave date, if applicable.
            - action_maker_id (str): Identifier of the person who took action on the leave.
            - act_maker_name (str): Name of the approver/action taker.
            - action_date (str): Date when the action was taken (MM/DD/YYYY).
            - action_comment (str): Comment added by the approver.
            - can_cancel (bool): Whether the leave can be cancelled by the employee.
            - can_act (bool): Whether the current user can take action on the leave.
    """
    user, error = resolve_user(query)
    if error:
        return error
    return get_employee_leaves(
        user_id=user["user_id"],
        signed_array=user["signed_array"],
        start_date=start_date,
        end_date=end_date
    )

@tool(args_schema=FindUserLeavesPolicyInput)
def get_employee_leaves_policy_tool(
    query: str,
) -> dict:
    """
    Retrieve the leave policy configuration applicable to a specific employee.

    Args:
        query (str): Name, user_id, or employee_id to identify the employee.

    Returns:
        dict: An object representing the employee's leave policy.

        The returned policy object contains:
            - policy_id (str): Unique identifier of the leave policy.

            Leave balance limits:
            - cal_max_bal (int): Maximum Casual Leave balance allowed.
            - eml_max_bal (int): Maximum Emergency Leave balance allowed.
            - exl_max_bal (int): Maximum Extra Leave balance allowed.
            - cff_max_bal (int): Maximum Comp-Off balance allowed.

            Leave usage constraints:
            - max_cal_taken_together (str): Maximum casual leaves allowed together.
            - max_exl_taken_together (str): Maximum extra leaves allowed together.
            - min_exl_taken_together (str): Minimum extra leaves required in one request.
            - max_cff_taken_in_a_month (str): Maximum comp-off leaves allowed per month.

            Carry forward rules:
            - max_cal_carry_forward (int | None): Maximum casual leaves carried forward.
            - max_exl_carry_forward (int | None): Maximum extra leaves carried forward.
            - max_eml_carry_forward (int | None): Maximum emergency leaves carried forward.

            Advance leave application rules (in days):
            - apply_cal_half_before (str): Days before applying half-day casual leave.
            - apply_cal_before (str): Days before applying casual leave.
            - apply_eml_before (str): Days before applying emergency leave.
            - apply_exl_before (str): Days before applying extra leave.

            Deduction and penalty rules:
            - eml_transfer_deduction (float): Deduction rate when emergency leave is transferred.
            - exl_transfer_deduction (float): Deduction rate when extra leave is transferred.
            - unapproved_deduction_rate (float): Deduction multiplier for unapproved leaves.
            - insufficient_approved_deduction_rate (float): Deduction rate when approvals are insufficient.

            Comp-Off and expiry rules:
            - cff_expiry_limit (str): Comp-off expiry duration in days.

            Attendance and system rules:
            - enabled_sandwich_rule (str): Whether sandwich leave rule is enabled ("1"/"0").
            - max_att_override (str): Maximum attendance overrides allowed.
            - att_overtime_hour (str): Overtime hours threshold.
            - checkin_relaxation_time (str): Allowed late check-in relaxation time (minutes).
            - max_week_off (str): Maximum allowed week-offs.
            - default_week_off_days (list[str]): Default week-off days (1=Monday … 7=Sunday).

            Notification and audit metadata:
            - leave_req_mail_id (str): Email address for leave request notifications.
            - modified_by (str): User ID of the person who last modified the policy.
            - modified_on (str): Timestamp of the last modification (YYYY-MM-DD HH:MM:SS).

    Note:
        - Policy values are enforced system-wide by HRMS.
        - Some numeric values may be returned as strings depending on backend configuration.
    """
    user, error = resolve_user(query)
    if error:
        return error
    return get_employee_leaves_policy(
        user_id=user["user_id"],
        signed_array=user["signed_array"],
    )

@tool(args_schema=EmpHolidaysAndLeaveCalendarInput)
def get_holiday_and_leave_calendar_tool(
    query: str,
    start_date: str = "",
    end_date: str = ""
) -> dict:
    """
    Retrieve the holiday calendar and employee leave calendar for a given user
    within an optional date range.

    This tool provides information about organizational holidays, weekly offs,
    and a mapping of dates to employees who are on leave.

    Args:
        query (str): Name, user_id, or employee_id to identify the user.
        start_date (str, optional): Start date filter in MM/DD/YYYY format.
        end_date (str, optional): End date filter in MM/DD/YYYY format.

    Returns:
        dict: An object containing holiday and leave calendar information.

        The response contains the following keys:

        holidays (list[dict]):
            List of organizational holidays and weekly offs.

            Each holiday object includes:
                - name (str): Holiday or week-off name
                    (e.g., "Diwali", "Independence Day", "2nd Saturday").
                - date (str): Date of the holiday (MM/DD/YYYY).

        leaves (dict[str, list[str]]):
            A mapping of dates to a list of employee names who are on leave.

            - Key (str): Date in MM/DD/YYYY format.
            - Value (list[str]): Names of employees on leave on that date.
    """
    user, error = resolve_user(query)
    if error:
        return error
    return get_holiday_and_leave_calendar(
        user_id=user["user_id"],
        signed_array=user["signed_array"],
        start_date=start_date,
        end_date=end_date
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
    get_employee_leaves_tool,
    get_employee_leaves_policy_tool,
    get_holiday_and_leave_calendar_tool,
]