import requests
from datetime import datetime, timedelta
from db import db
from config import CONFIG

DRIVE_FILES_URL = "https://www.googleapis.com/drive/v3/files"
SHEETS_API_BASE = "https://sheets.googleapis.com/v4/spreadsheets"


def list_google_spreadsheets(
    access_token: str,
    limit: int = 25,
    search: str | None = None,
) -> list[dict]:
    """
    Return Google Sheets files accessible to the user.

    Args:
        limit:  Maximum number of results to return (default 25, max 100).
        search: Optional name substring filter (case-insensitive on Google's side).
    """
    q = "mimeType='application/vnd.google-apps.spreadsheet' and trashed=false"
    if search and search.strip():
        safe = search.strip().replace("'", "\\'")
        q += f" and name contains '{safe}'"

    params = {
        "q": q,
        "fields": "files(id,name)",
        "orderBy": "modifiedTime desc",
        "pageSize": min(max(1, limit), 100),
    }
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.get(DRIVE_FILES_URL, headers=headers, params=params)
    if response.status_code != 200:
        raise RuntimeError(f"Google Drive API error: {response.text}")
    return response.json().get("files", [])


def list_spreadsheet_sheets(access_token: str, spreadsheet_id: str) -> list[dict]:
    """Return all sheet tabs in a spreadsheet as [{id, title}]."""
    url = f"{SHEETS_API_BASE}/{spreadsheet_id}"
    # Fetch only sheet properties — no fields mask to avoid format issues
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        raise RuntimeError(f"Google Sheets API error ({response.status_code}): {response.text}")
    data = response.json()
    sheets = data.get("sheets", [])
    return [
        {"id": s["properties"]["title"], "label": s["properties"]["title"]}
        for s in sheets
        if s.get("properties", {}).get("title")
    ]


def get_sheet_column_headers(access_token: str, spreadsheet_id: str, sheet_name: str) -> list[str]:
    """Fetch the first row of a sheet and return the non-empty header column names."""
    range_notation = f"'{sheet_name}'!1:1"
    url = f"{SHEETS_API_BASE}/{spreadsheet_id}/values/{requests.utils.quote(range_notation, safe='')}"
    headers = {"Authorization": f"Bearer {access_token}"}
    response = requests.get(url, headers=headers)
    if response.status_code != 200:
        raise RuntimeError(f"Google Sheets API error: {response.text}")
    rows = response.json().get("values", [])
    if not rows:
        return []
    return [str(h).strip() for h in rows[0] if str(h).strip()]


def append_row_to_sheet(
    access_token: str,
    spreadsheet_id: str,
    sheet_name: str,
    row_values: list,
) -> dict:
    """Append a row after the last data row using the Sheets values.append API."""
    range_notation = f"'{sheet_name}'"
    url = (
        f"{SHEETS_API_BASE}/{spreadsheet_id}/values/"
        f"{requests.utils.quote(range_notation, safe='')}:append"
    )
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    params = {
        "valueInputOption": "USER_ENTERED",
        "insertDataOption": "INSERT_ROWS",
    }
    payload = {"values": [row_values]}
    response = requests.post(url, headers=headers, params=params, json=payload)
    if response.status_code not in (200, 201):
        raise RuntimeError(f"Google Sheets append error: {response.text}")
    return response.json()


def insert_row_after_first(
    access_token: str,
    spreadsheet_id: str,
    sheet_name: str,
    row_values: list,
) -> dict:
    """
    Insert a new blank row at position 2 (index 1, 0-based), then write data into it.
    This pushes all existing rows down by one.
    """
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }

    # First, find the numeric sheet ID for the target sheet (needed by batchUpdate)
    meta_url = f"{SHEETS_API_BASE}/{spreadsheet_id}"
    meta_resp = requests.get(
        meta_url,
        headers={"Authorization": f"Bearer {access_token}"},
        params={"fields": "sheets.properties(sheetId,title)"},
    )
    if meta_resp.status_code != 200:
        raise RuntimeError(f"Google Sheets API error fetching sheet metadata: {meta_resp.text}")

    sheet_id_int = None
    for s in meta_resp.json().get("sheets", []):
        if s["properties"]["title"] == sheet_name:
            sheet_id_int = s["properties"]["sheetId"]
            break
    if sheet_id_int is None:
        raise RuntimeError(f"Sheet '{sheet_name}' not found in spreadsheet.")

    # Insert 1 row at index 1 (after header row at index 0)
    batch_url = f"{SHEETS_API_BASE}/{spreadsheet_id}:batchUpdate"
    batch_payload = {
        "requests": [
            {
                "insertDimension": {
                    "range": {
                        "sheetId": sheet_id_int,
                        "dimension": "ROWS",
                        "startIndex": 1,
                        "endIndex": 2,
                    },
                    "inheritFromBefore": False,
                }
            }
        ]
    }
    batch_resp = requests.post(batch_url, headers=headers, json=batch_payload)
    if batch_resp.status_code not in (200, 201):
        raise RuntimeError(f"Google Sheets batchUpdate error: {batch_resp.text}")

    # Now write the row values into the newly inserted row 2
    range_notation = f"'{sheet_name}'!A2"
    update_url = (
        f"{SHEETS_API_BASE}/{spreadsheet_id}/values/"
        f"{requests.utils.quote(range_notation, safe='')}"
    )
    update_payload = {"values": [row_values]}
    update_resp = requests.put(
        update_url,
        headers=headers,
        params={"valueInputOption": "USER_ENTERED"},
        json=update_payload,
    )
    if update_resp.status_code not in (200, 201):
        raise RuntimeError(f"Google Sheets update error: {update_resp.text}")
    return update_resp.json()


def refresh_google_sheets_access_token_if_expired(user_id: str, integration: dict) -> dict | None:
    """Checks if the access token is expired and refreshes it if needed for Google Sheets."""
    expires_at_str = integration.get("expires_at")
    if not expires_at_str:
        return integration

    expires_at = datetime.fromisoformat(expires_at_str.replace("Z", "+00:00"))
    if datetime.utcnow().replace(tzinfo=None) < expires_at.replace(tzinfo=None):
        return integration

    refresh_token = integration.get("refresh_token")
    if not refresh_token:
        print("No refresh token available for Google Sheets integration.")
        return None

    token_url = "https://oauth2.googleapis.com/token"
    data = {
        "client_id": CONFIG.GOOGLE_OAUTH_CLIENT_ID,
        "client_secret": CONFIG.GOOGLE_OAUTH_CLIENT_SECRET,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }
    response = requests.post(token_url, data=data)
    if response.status_code != 200:
        print(f"Failed to refresh Google Sheets token: {response.text}")
        return None

    token_data = response.json()
    new_expires_in = token_data.get("expires_in", 3600)
    new_expires_at = (datetime.utcnow() + timedelta(seconds=new_expires_in)).isoformat() + "Z"

    updated_tokens = {
        "access_token": token_data.get("access_token"),
        "refresh_token": token_data.get("refresh_token", refresh_token),
        "expires_at": new_expires_at,
    }
    db.integration.save_integration_tokens(user_id, "google_sheets", updated_tokens)
    print(
        f"[Google Sheets Refresh] Token refreshed for user {user_id}. "
        f"New expires_at: {new_expires_at}"
    )
    return {**integration, **updated_tokens}
