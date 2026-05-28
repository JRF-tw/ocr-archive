import datetime
from googleapiclient.discovery import build


class GoogleSheetsClient:
    def __init__(self, credentials):
        self.service = build("sheets", "v4", credentials=credentials)

    def ensure_tab(self, spreadsheet_id: str, tab: str, headers: list[str] | None = None):
        meta = self.service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        existing = [s["properties"]["title"] for s in meta.get("sheets", [])]
        if tab not in existing:
            self.service.spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id,
                body={"requests": [{"addSheet": {"properties": {"title": tab}}}]},
            ).execute()
        if headers:
            self.service.spreadsheets().values().update(
                spreadsheetId=spreadsheet_id,
                range=f"{tab}!A1",
                valueInputOption="RAW",
                body={"values": [headers]},
            ).execute()

    def _get_rows(self, spreadsheet_id: str, tab: str) -> list[dict]:
        result = self.service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=f"{tab}!A:H",
        ).execute()
        rows = result.get("values", [])
        if not rows:
            return []
        headers = rows[0]
        return [
            dict(zip(headers, row + [""] * (len(headers) - len(row))))
            for row in rows[1:]
        ]

    def get_pending_jobs(self, spreadsheet_id: str, tab: str) -> list[dict]:
        """Return rows from the Queue tab where status is 'pending'."""
        try:
            return [r for r in self._get_rows(spreadsheet_id, tab) if r.get("status") == "pending"]
        except Exception as e:
            raise RuntimeError(f"Failed to get pending jobs from {spreadsheet_id}/{tab}: {e}") from e

    def get_running_jobs(self, spreadsheet_id: str, tab: str) -> list[dict]:
        """Return rows from the Queue tab where status is 'running'."""
        try:
            return [r for r in self._get_rows(spreadsheet_id, tab) if r.get("status") == "running"]
        except Exception as e:
            raise RuntimeError(f"Failed to get running jobs: {e}") from e

    def get_failed_jobs(self, spreadsheet_id: str, tab: str) -> list[dict]:
        """Return rows from the Queue tab where status is 'failed'."""
        try:
            return [r for r in self._get_rows(spreadsheet_id, tab) if r.get("status") == "failed"]
        except Exception as e:
            raise RuntimeError(f"Failed to get failed jobs: {e}") from e

    def update_job_status(
        self,
        spreadsheet_id: str,
        tab: str,
        file_id: str,
        status: str,
        started_at: str | None = None,
        completed_at: str | None = None,
        work_dir: str | None = None,
        error: str | None = None,
    ):
        result = self.service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=f"{tab}!A:H",
        ).execute()
        rows = result.get("values", [])
        if not rows:
            return
        headers = rows[0]
        for i, row in enumerate(rows[1:], start=2):
            record = dict(zip(headers, row + [""] * (len(headers) - len(row))))
            if record.get("file_id") == file_id:
                updates = {"status": status}
                if started_at is not None:
                    updates["started_at"] = started_at
                if completed_at is not None:
                    updates["completed_at"] = completed_at
                if work_dir is not None:
                    updates["work_dir"] = work_dir
                if error is not None:
                    updates["error"] = error
                for col, val in updates.items():
                    if col in headers:
                        col_idx = headers.index(col)
                        col_letter = chr(ord("A") + col_idx)
                        self.service.spreadsheets().values().update(
                            spreadsheetId=spreadsheet_id,
                            range=f"{tab}!{col_letter}{i}",
                            valueInputOption="RAW",
                            body={"values": [[val]]},
                        ).execute()
                return

    def append_rows(self, spreadsheet_id: str, tab: str, rows: list[list]):
        self.service.spreadsheets().values().append(
            spreadsheetId=spreadsheet_id,
            range=f"{tab}!A1",
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": rows},
        ).execute()
