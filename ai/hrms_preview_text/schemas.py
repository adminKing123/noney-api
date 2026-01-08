from pydantic import BaseModel, Field
from typing import Optional, Literal

class FindUserInput(BaseModel):
    query: str = Field(
        description="Name, user_id, employee_id or email to search for. Supports partial name matching and exact ID matching."
    )

class FindUserLeavesPolicyInput(BaseModel):
    query: str = Field(
        description="Name, user_id, employee_id or email of the user to get leave policy for."
    )

class TodayLogStatusInput(BaseModel):
    query: str = Field(
        description="Name, user_id, employee_id or email of the user to check today's attendance logs for."
    )

class EmpProjectsInput(BaseModel):
    query: str = Field(
        description="Name, user_id, employee_id or email of the employee whose projects you want to fetch."
    )

class EmpProjectLogInput(BaseModel):
    query: str = Field(
        description="Name, user_id, employee_id or email of the employee whose work logs you want to retrieve."
    )
    project_id: Optional[str] = Field(
        default="0",
        description="Project ID to filter logs. Use 0 or omit to fetch logs from all projects."
    )
    start_date: Optional[str] = Field(
        default="",
        description="Start date for filtering logs in YYYY-MM-DD format. Leave empty for no start date filter."
    )
    end_date: Optional[str] = Field(
        default="",
        description="End date for filtering logs in YYYY-MM-DD format. Leave empty for no end date filter."
    )

class UserMailSettingInput(BaseModel):
    query: str = Field(
        description="Name, user_id, employee_id or email of the user whose email notification preferences you want to retrieve."
    )

class AttendanceInput(BaseModel):
    query: str = Field(
        description="Name, user_id, employee_id or email of the user whose attendance records you want to retrieve."
    )
    start_date: Optional[str] = Field(
        default="",
        description="Start date filter in YYYY-MM-DD format. Leave empty to get all records from the beginning."
    )
    end_date: Optional[str] = Field(
        default="",
        description="End date filter in YYYY-MM-DD format. Leave empty to get all records up to now."
    )

class FetchDataInput(BaseModel):
    endpoint: str = Field(
        description="API endpoint path to call (e.g., '/attendance/show_attendance'). Must start with /."
    )
    user_id: Optional[str] = Field(
        default=None,
        description="Optional user_id override. Leave empty to use default."
    )
    signed_array: Optional[str] = Field(
        default=None,
        description="Optional authentication token override. Leave empty to use default."
    )

class LoginInput(BaseModel):
    query: str = Field(
        description="Name, user_id, employee_id or email of the user to check in (login)."
    )
    override_comment: Optional[str] = Field(
        default="",
        description="Optional comment to attach to the login action (e.g., reason for late arrival)."
    )
    today_login_status: Literal["logged_in", "logged_out"] = Field(
        description="Current login status of the user for today. get it using get_today_log_status_tool tool."
    )

class LogoutInput(BaseModel):
    query: str = Field(
        description="Name, user_id, employee_id or email of the user to check out (logout)."
    )
    override_comment: Optional[str] = Field(
        default="",
        description="Optional comment to attach to the logout action (e.g., reason for early departure)."
    )
    today_login_status: Literal["logged_in", "logged_out"] = Field(
        description="Current login status of the user for today. get it using get_today_log_status_tool tool."
    )

class ProjectModulesInput(BaseModel):
    query: str = Field(
        description="Name, user_id, employee_id or email of the user."
    )
    project_id: Optional[str] = Field(
        default=None,
        description="Project ID to fetch modules for. Required to get meaningful results."
    )

class ProjectActivitiesInput(BaseModel):
    query: str = Field(
        description="Name, user_id, employee_id or email of the user."
    )
    project_id: Optional[str] = Field(
        default=None,
        description="Project ID to fetch activities for. Required to get meaningful results."
    )

class EmpLeavesInput(BaseModel):
    query: str = Field(
        description="Name, user_id, employee_id or email of the employee whose leaves you want to retrieve."
    )
    start_date: str = Field(
        description="Start date in MM/DD/YYYY format."
    )
    end_date: str = Field(
        description="End date in MM/DD/YYYY format."
    )

class EmpHolidaysAndLeaveCalendarInput(BaseModel):
    query: str = Field(
        description="Name, user_id, employee_id or email of the employee whose holidays and leave calendar you want to retrieve."
    )
    start_date: str = Field(
        description="Start date in MM/DD/YYYY format."
    )
    end_date: str = Field(
        description="End date in MM/DD/YYYY format."
    )

class EmpWebexTokenInput(BaseModel):
    query: str = Field(
        description="Name, user_id, employee_id or email of the employee whose Webex token you want to retrieve."
    )



# Work Log Input Schema

class ProjectInput(BaseModel):
    project_id: str = Field(
        default=None,
        description="Project ID. If not provided, resolve using project_name via get_emp_projects_tool."
    )
    project_name: str = Field(
        default=None,
        description="Original project name that is found using project_id from get_emp_projects_tool."
    )

class ModuleInput(BaseModel):
    module_id: str = Field(
        description="Module ID. If not provided, resolve using module_name via get_project_modules_tool."
    )
    module_name: str = Field(
        description="Original module name that is found using module_id from get_project_modules_tool."
    )

class ActivityInput(BaseModel):
    activity_id: str = Field(
        description="Activity ID. If not provided, resolve using activity_name via get_project_activities_tool."
    )
    activity_name: str = Field(
        description="Original activity name that is found using activity_id from get_project_activities_tool."
    )


class WorkLogInput(BaseModel):
    query: str = Field(
        description="Name, user_id, employee_id or email of the employee whose work is being logged."
    )

    project: ProjectInput = Field(
        description="Resolve using get_emp_projects_tool"
    )

    module: ModuleInput = Field(
        description="Resolve using get_project_modules_tool"
    )

    activity: ActivityInput = Field(
        description="Resolve using get_project_activities_tool"
    )
    hour_clocked: float = Field(
        description="Number of hours to log."
    )
    work_desc: str = Field(
        description="Description of the work done."
    )
