"""Shared Google API authentication helper."""

from __future__ import annotations

from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = [
    "https://www.googleapis.com/auth/drive",
    "https://www.googleapis.com/auth/spreadsheets",
]


def _build_credentials(
    credentials_path: Path, token_path: Path, scopes: list[str]
) -> Credentials:
    """Build or refresh Google API credentials.

    Three-way flow:
      1. Load existing token and reuse if still valid.
      2. If expired but has refresh_token, refresh it.
      3. Otherwise run browser-based OAuth flow.
    """
    creds: Credentials | None = None

    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), scopes)

    if creds and creds.valid:
        return creds

    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        token_path.write_text(creds.to_json())
        return creds

    flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), scopes)
    creds = flow.run_local_server(port=0)
    token_path.write_text(creds.to_json())
    return creds
