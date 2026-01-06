from pydantic import BaseModel, Field
from typing import Optional

class FindUserInput(BaseModel):
    query: str = Field(
        description="Name, user_id, or employee_id to search for. Supports partial name matching and exact ID matching."
    )

class FindUserLeavesPolicyInput(BaseModel):
    query: str = Field(
        description="Name, user_id, or employee_id of the user to get leave policy for."
    )

class TodayLogStatusInput(BaseModel):
    query: str = Field(
        description="Name, user_id, or employee_id of the user to check today's attendance logs for."
    )

class EmpProjectsInput(BaseModel):
    query: str = Field(
        description="Name, user_id, or employee_id of the employee whose projects you want to fetch."
    )

class EmpProjectLogInput(BaseModel):
    query: str = Field(
        description="Name, user_id, or employee_id of the employee whose work logs you want to retrieve."
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
        description="Name, user_id, or employee_id of the user whose email notification preferences you want to retrieve."
    )

class AttendanceInput(BaseModel):
    query: str = Field(
        description="Name, user_id, or employee_id of the user whose attendance records you want to retrieve."
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
        description="Name, user_id, or employee_id of the user to check in (login)."
    )
    override_comment: Optional[str] = Field(
        default="",
        description="Optional comment to attach to the login action (e.g., reason for late arrival)."
    )

class LogoutInput(BaseModel):
    query: str = Field(
        description="Name, user_id, or employee_id of the user to check out (logout)."
    )
    override_comment: Optional[str] = Field(
        default="",
        description="Optional comment to attach to the logout action (e.g., reason for early departure)."
    )

class ProjectModulesInput(BaseModel):
    query: str = Field(
        description="Name, user_id, or employee_id of the user."
    )
    project_id: Optional[str] = Field(
        default=None,
        description="Project ID to fetch modules for. Required to get meaningful results."
    )

class ProjectActivitiesInput(BaseModel):
    query: str = Field(
        description="Name, user_id, or employee_id of the user."
    )
    project_id: Optional[str] = Field(
        default=None,
        description="Project ID to fetch activities for. Required to get meaningful results."
    )

class EmpLeavesInput(BaseModel):
    query: str = Field(
        description="Name, user_id, or employee_id of the employee whose leaves you want to retrieve."
    )
    start_date: str = Field(
        description="Start date in MM/DD/YYYY format."
    )
    end_date: str = Field(
        description="End date in MM/DD/YYYY format."
    )

class EmpHolidaysAndLeaveCalendarInput(BaseModel):
    query: str = Field(
        description="Name, user_id, or employee_id of the employee whose holidays and leave calendar you want to retrieve."
    )
    start_date: str = Field(
        description="Start date in MM/DD/YYYY format."
    )
    end_date: str = Field(
        description="End date in MM/DD/YYYY format."
    )
