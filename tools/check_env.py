#!/usr/bin/env python3
"""Verify that the JRF OCR pipeline environment is correctly configured.

Checks:
  1. Required CLI tools (pdftoppm)
  2. ~/.jrf/credentials.json  — OAuth client secrets
  3. ~/.jrf/drive_config.json — pipeline config (all required fields)
  4. Google Drive API reachable + input/output folders accessible
  5. Google Sheets API reachable + spreadsheet has Queue and Archive tabs

Usage:
    uv run python -m tools.check_env
"""

import json
import shutil
import sys
from pathlib import Path

CREDENTIALS_PATH = Path("~/.jrf/credentials.json").expanduser()
CONFIG_PATH = Path("~/.jrf/drive_config.json").expanduser()
REQUIRED_CONFIG_KEYS = ["work_root", "input_folder_id", "output_folder_id", "spreadsheet_id", "queue_tab", "archive_tab"]

OK   = "\033[32m✓\033[0m"
FAIL = "\033[31m✗\033[0m"
WARN = "\033[33m!\033[0m"

errors = 0


def ok(msg: str) -> None:
    print(f"  {OK}  {msg}")


def fail(msg: str) -> None:
    global errors
    errors += 1
    print(f"  {FAIL}  {msg}")


def warn(msg: str) -> None:
    print(f"  {WARN}  {msg}")


# ── 1. CLI tools ──────────────────────────────────────────────────────────────
print("\n[1] CLI tools")
if shutil.which("pdftoppm"):
    ok("pdftoppm found")
else:
    fail("pdftoppm not found — install poppler (brew install poppler)")

# ── 2. credentials.json ───────────────────────────────────────────────────────
print("\n[2] OAuth credentials  (~/.jrf/credentials.json)")
creds_ok = False
if not CREDENTIALS_PATH.exists():
    fail(f"File not found: {CREDENTIALS_PATH}")
else:
    try:
        creds_data = json.loads(CREDENTIALS_PATH.read_text())
        top_key = list(creds_data.keys())[0]  # "installed" or "web"
        client_id = creds_data[top_key].get("client_id", "")
        ok(f"File present  (type={top_key}, client_id=…{client_id[-8:]})")
        creds_ok = True
    except Exception as e:
        fail(f"Could not parse credentials.json: {e}")

# ── 3. drive_config.json ──────────────────────────────────────────────────────
print("\n[3] Drive config  (~/.jrf/drive_config.json)")
cfg = {}
if not CONFIG_PATH.exists():
    fail(f"File not found: {CONFIG_PATH}")
else:
    try:
        cfg = json.loads(CONFIG_PATH.read_text())
        ok("File present")
        for key in REQUIRED_CONFIG_KEYS:
            val = cfg.get(key, "")
            if not val or val == "FILL_IN":
                fail(f"  {key} is not set")
            else:
                ok(f"  {key} = {val}")
    except Exception as e:
        fail(f"Could not parse drive_config.json: {e}")

# ── 4 & 5. API connectivity ───────────────────────────────────────────────────
if not creds_ok or not cfg:
    warn("Skipping API checks (credentials or config missing)")
    print()
else:
    try:
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.auth.transport.requests import Request
        from googleapiclient.discovery import build

        TOKEN_PATH = Path("~/.jrf/token.json").expanduser()
        SCOPES = [
            "https://www.googleapis.com/auth/drive",
            "https://www.googleapis.com/auth/spreadsheets",
        ]

        creds = None
        if TOKEN_PATH.exists():
            creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
                TOKEN_PATH.write_text(creds.to_json())
            else:
                print("\n  → Opening browser for Google OAuth…")
                flow = InstalledAppFlow.from_client_secrets_file(str(CREDENTIALS_PATH), SCOPES)
                creds = flow.run_local_server(port=0)
                TOKEN_PATH.write_text(creds.to_json())

        # ── 4. Drive ─────────────────────────────────────────────────────────
        print("\n[4] Google Drive API")
        drive_svc = build("drive", "v3", credentials=creds)

        for label, folder_key in [("input_folder_id", "input"), ("output_folder_id", "output")]:
            folder_id = cfg.get(label, "")
            if not folder_id:
                continue
            try:
                meta = drive_svc.files().get(fileId=folder_id, fields="name,mimeType").execute()
                if meta.get("mimeType") == "application/vnd.google-apps.folder":
                    ok(f"{folder_key} folder accessible: '{meta['name']}'")
                else:
                    fail(f"{folder_key} ID is not a folder (mimeType={meta.get('mimeType')})")
            except Exception as e:
                fail(f"{folder_key} folder not accessible: {e}")

        # ── 5. Sheets ─────────────────────────────────────────────────────────
        print("\n[5] Google Sheets API")
        sheets_svc = build("sheets", "v4", credentials=creds)
        spreadsheet_id = cfg.get("spreadsheet_id", "")
        queue_tab  = cfg.get("queue_tab",  "Queue")
        archive_tab = cfg.get("archive_tab", "Archive")

        try:
            meta = sheets_svc.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
            title = meta.get("properties", {}).get("title", "?")
            ok(f"Spreadsheet accessible: '{title}'")

            sheet_names = {s["properties"]["title"] for s in meta.get("sheets", [])}
            missing_tabs = [t for t in [queue_tab, archive_tab] if t not in sheet_names]
            if missing_tabs:
                add_requests = [{"addSheet": {"properties": {"title": t}}} for t in missing_tabs]
                sheets_svc.spreadsheets().batchUpdate(
                    spreadsheetId=spreadsheet_id,
                    body={"requests": add_requests},
                ).execute()
                for t in missing_tabs:
                    ok(f"  Tab '{t}' created")
            for tab in [queue_tab, archive_tab]:
                if tab not in missing_tabs:
                    ok(f"  Tab '{tab}' exists")
        except Exception as e:
            fail(f"Spreadsheet not accessible: {e}")

    except ImportError as e:
        fail(f"Missing Python package: {e}  — run: uv sync")

# ── Summary ───────────────────────────────────────────────────────────────────
print()
if errors == 0:
    print(f"{OK}  All checks passed — environment is ready.\n")
else:
    print(f"{FAIL}  {errors} check(s) failed — fix the issues above and re-run.\n")
    sys.exit(1)
