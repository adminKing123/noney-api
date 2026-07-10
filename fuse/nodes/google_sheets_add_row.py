"""
fuse/nodes/google_sheets_add_row.py
====================================
Handler for the "Add Row" Google Sheets action node.

Config keys
-----------
spreadsheet_id : str  — Google Sheets file ID (selected from picker)
sheet_name     : str  — Sheet tab name
add_row        : str  — "after_last" | "after_first"
column_data    : dict — { "Column Header": "value or {{variable}}" }
"""

import logging
import requests

from .base import NodeHandler
from ..executor import ExecutionContext
from ..variable_resolver import resolve_variables
from db import db
from utils.integrations.google_sheets_utils import (
    refresh_google_sheets_access_token_if_expired,
    get_sheet_column_headers,
    append_row_to_sheet,
    insert_row_after_first,
)

logger = logging.getLogger(__name__)


class GoogleSheetsAddRowHandler(NodeHandler):
    node_type = "google_sheets_add_row"

    def execute(self, config: dict, context: ExecutionContext) -> dict:
        outputs = context.node_outputs

        spreadsheet_id = resolve_variables(config.get("spreadsheet_id", ""), outputs)
        sheet_name     = resolve_variables(config.get("sheet_name", ""), outputs)
        add_row        = config.get("add_row", "after_last")
        column_data    = config.get("column_data") or {}

        if not spreadsheet_id:
            raise ValueError("Missing 'spreadsheet_id' — select a spreadsheet in the node config.")
        if not sheet_name:
            raise ValueError("Missing 'sheet_name' — select a sheet tab in the node config.")

        if not context.owner_id:
            raise ValueError("No owner_id in execution context; cannot retrieve Google Sheets integration.")

        integration = db.integration.get_integration(context.owner_id, "google_sheets")
        if not integration or not integration.get("configured"):
            raise ValueError("Google Sheets integration is not configured for this user.")

        integration = refresh_google_sheets_access_token_if_expired(context.owner_id, integration)
        if not integration or not integration.get("access_token"):
            raise ValueError("Failed to obtain a valid Google Sheets access token. Please re-authenticate.")

        access_token = integration["access_token"]

        # Fetch column headers so we know the exact column order
        try:
            headers = get_sheet_column_headers(access_token, spreadsheet_id, sheet_name)
        except RuntimeError as exc:
            raise RuntimeError(f"Could not fetch column headers: {exc}") from exc

        # Resolve variable tokens inside every column value
        resolved: dict[str, str] = {}
        for col_name, col_value in column_data.items():
            resolved[col_name] = resolve_variables(str(col_value) if col_value is not None else "", outputs)

        # Build an ordered list of values aligned to the header row
        # Columns that are not in column_data are sent as empty strings
        row_values = [resolved.get(h, "") for h in headers]

        logger.info(
            "[FUSE] google_sheets_add_row: spreadsheet=%s sheet=%s position=%s columns=%s "
            "(workflow=%s run=%s)",
            spreadsheet_id, sheet_name, add_row, list(resolved.keys()),
            context.workflow_id, context.run_id,
        )

        try:
            if add_row == "after_first":
                result = insert_row_after_first(access_token, spreadsheet_id, sheet_name, row_values)
            else:
                result = append_row_to_sheet(access_token, spreadsheet_id, sheet_name, row_values)
        except RuntimeError as exc:
            raise RuntimeError(f"Google Sheets API error: {exc}") from exc

        return {
            "success": True,
            "spreadsheet_id": spreadsheet_id,
            "sheet_name": sheet_name,
            "row_position": add_row,
            "columns_written": list(resolved.keys()),
            "updated_range": result.get("updates", {}).get("updatedRange")
                             or result.get("updatedRange", ""),
        }
