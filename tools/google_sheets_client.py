"""Google Sheets API client for the JRF OCR pipeline."""

from __future__ import annotations

import csv
from pathlib import Path

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

from tools._auth import SCOPES, _build_credentials


def _col_to_a1(col: int) -> str:
    """Convert a 1-based column number to A1-notation letter(s).

    Examples: 1 → A, 26 → Z, 27 → AA, 28 → AB.
    """
    result = ""
    while col > 0:
        col, remainder = divmod(col - 1, 26)
        result = chr(65 + remainder) + result
    return result


class GoogleSheetsClient:
    """Wrapper around the Google Sheets v4 API."""

    def __init__(self, credentials_path: Path, token_path: Path) -> None:
        creds = _build_credentials(credentials_path, token_path, SCOPES)
        self.service = build("sheets", "v4", credentials=creds)
        self.sheets = self.service.spreadsheets()

    def get_pending_jobs(self, spreadsheet_id: str, tab: str) -> list[dict]:
        """Return rows from the Queue tab where status is 'pending'."""
        try:
            result = (
                self.sheets.values()
                .get(spreadsheetId=spreadsheet_id, range=tab)
                .execute()
            )
            rows = result.get("values", [])
            if not rows:
                return []

            headers = rows[0]
            pending: list[dict] = []
            for row in rows[1:]:
                padded = row + [""] * (len(headers) - len(row))
                record = dict(zip(headers, padded))
                if record.get("status") == "pending":
                    pending.append(record)
            return pending
        except HttpError as e:
            raise RuntimeError(
                f"Failed to get pending jobs from {spreadsheet_id}/{tab}: {e}"
            ) from e

    def update_job_status(
        self, spreadsheet_id: str, tab: str, file_id: str, status: str, **fields
    ) -> None:
        """Update the status (and optional extra fields) for a job row identified by file_id."""
        try:
            all_values = (
                self.sheets.values()
                .get(spreadsheetId=spreadsheet_id, range=tab)
                .execute()
            )
            rows = all_values.get("values", [])
            if not rows:
                raise RuntimeError(f"Tab '{tab}' is empty, cannot update job status")

            headers = rows[0]
            row_num = None
            for i, row in enumerate(rows[1:], start=2):
                if row and row[0] == file_id:
                    row_num = i
                    break
            if row_num is None:
                raise RuntimeError(
                    f"file_id '{file_id}' not found in {spreadsheet_id}/{tab}"
                )

            updates = {"status": status, **fields}
            for field_name, value in updates.items():
                if field_name not in headers:
                    continue
                col_index = headers.index(field_name)
                self.update_cell(spreadsheet_id, tab, row_num, col_index + 1, value)
        except HttpError as e:
            raise RuntimeError(
                f"Failed to update job status for file_id '{file_id}' in {spreadsheet_id}/{tab}: {e}"
            ) from e

    def ensure_tab(
        self, spreadsheet_id: str, tab_name: str, header_row: list[str] | None = None
    ) -> None:
        """Ensure a tab exists in the spreadsheet. Only writes headers to newly-created tabs."""
        try:
            sheet_metadata = self.sheets.get(spreadsheetId=spreadsheet_id).execute()
            existing_tabs = [
                s["properties"]["title"]
                for s in sheet_metadata.get("sheets", [])
            ]

            if tab_name in existing_tabs:
                return

            body = {
                "requests": [
                    {
                        "addSheet": {
                            "properties": {"title": tab_name}
                        }
                    }
                ]
            }
            self.sheets.batchUpdate(
                spreadsheetId=spreadsheet_id, body=body
            ).execute()

            if header_row:
                self.sheets.values().update(
                    spreadsheetId=spreadsheet_id,
                    range=f"{tab_name}!A1",
                    valueInputOption="RAW",
                    body={"values": [header_row]},
                ).execute()
        except HttpError as e:
            raise RuntimeError(
                f"Failed to ensure tab '{tab_name}' in {spreadsheet_id}: {e}"
            ) from e

    def append_from_csv(
        self, spreadsheet_id: str, tab_name: str, csv_path: Path, skip_header: bool = True
    ) -> int:
        """Append rows from a CSV file to a sheet tab in a single batch API call."""
        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            all_rows = list(reader)

        if skip_header and all_rows:
            data_rows = all_rows[1:]
        else:
            data_rows = all_rows

        if not data_rows:
            return 0

        try:
            self.sheets.values().append(
                spreadsheetId=spreadsheet_id,
                range=f"{tab_name}!A1",
                valueInputOption="RAW",
                insertDataOption="INSERT_ROWS",
                body={"values": data_rows},
            ).execute()
            return len(data_rows)
        except HttpError as e:
            raise RuntimeError(
                f"Failed to append CSV rows to {spreadsheet_id}/{tab_name}: {e}"
            ) from e

    def find_rows_by_value(
        self, spreadsheet_id: str, tab_name: str, column_index: int, value: str
    ) -> list[int]:
        """Find all rows where the given column matches value. Returns 1-based row numbers."""
        try:
            result = (
                self.sheets.values()
                .get(spreadsheetId=spreadsheet_id, range=tab_name)
                .execute()
            )
            rows = result.get("values", [])
            matches: list[int] = []
            for i, row in enumerate(rows):
                if column_index < len(row) and row[column_index] == value:
                    matches.append(i + 1)  # 1-based
            return matches
        except HttpError as e:
            raise RuntimeError(
                f"Failed to find rows by value in {spreadsheet_id}/{tab_name}: {e}"
            ) from e

    def update_cell(
        self, spreadsheet_id: str, tab_name: str, row: int, col: int, value: str
    ) -> None:
        """Update a single cell. Row is 1-based, col is 1-based."""
        col_letter = _col_to_a1(col)
        cell_ref = f"{tab_name}!{col_letter}{row}"
        try:
            self.sheets.values().update(
                spreadsheetId=spreadsheet_id,
                range=cell_ref,
                valueInputOption="RAW",
                body={"values": [[value]]},
            ).execute()
        except HttpError as e:
            raise RuntimeError(
                f"Failed to update cell {cell_ref} in {spreadsheet_id}: {e}"
            ) from e

    def batch_update_cells(self, spreadsheet_id: str, updates: list[dict]) -> None:
        """Update multiple cells in one batch API call.

        Each update: {"range": "Tab!A1", "values": [[value]]}.
        """
        try:
            self.sheets.values().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={"data": updates, "valueInputOption": "RAW"},
            ).execute()
        except HttpError as e:
            raise RuntimeError(
                f"Failed to batch update cells in {spreadsheet_id}: {e}"
            ) from e

    @staticmethod
    def get_spreadsheet_url(spreadsheet_id: str) -> str:
        return f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit"
