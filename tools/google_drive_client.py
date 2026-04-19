"""Google Drive API client for the JRF OCR pipeline."""

from __future__ import annotations

import io
import mimetypes
from datetime import datetime
from pathlib import Path

from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload

from tools._auth import SCOPES, _build_credentials


class GoogleDriveClient:
    """Wrapper around the Google Drive v3 API."""

    def __init__(self, credentials_path: Path, token_path: Path) -> None:
        creds = _build_credentials(credentials_path, token_path, SCOPES)
        self.service = build("drive", "v3", credentials=creds)

    def list_pdfs_in_folder(
        self, folder_id: str, modified_after: datetime | None = None
    ) -> list[dict]:
        """List PDF files in a Drive folder."""
        q = (
            f"'{folder_id}' in parents "
            f"and mimeType='application/pdf' "
            f"and trashed=false"
        )
        if modified_after is not None:
            q += f" and modifiedTime > '{modified_after.isoformat()}'"
        try:
            results: list[dict] = []
            page_token: str | None = None
            while True:
                resp = (
                    self.service.files()
                    .list(
                        q=q,
                        fields="nextPageToken, files(id, name, modifiedTime, md5Checksum)",
                        pageToken=page_token,
                    )
                    .execute()
                )
                results.extend(resp.get("files", []))
                page_token = resp.get("nextPageToken")
                if not page_token:
                    break
            return results
        except HttpError as e:
            raise RuntimeError(
                f"Failed to list PDFs in folder {folder_id}: {e}"
            ) from e

    def get_file_metadata(self, file_id: str) -> dict:
        """Get metadata for a single file."""
        try:
            return (
                self.service.files()
                .get(
                    fileId=file_id,
                    fields="id,name,mimeType,size,md5Checksum,modifiedTime,webViewLink",
                )
                .execute()
            )
        except HttpError as e:
            raise RuntimeError(
                f"Failed to get metadata for file {file_id}: {e}"
            ) from e

    def download_file(self, file_id: str, dest_path: Path) -> Path:
        """Download a file from Drive to a local path."""
        try:
            request = self.service.files().get_media(fileId=file_id)
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            with open(dest_path, "wb") as fh:
                downloader = MediaIoBaseDownload(fh, request, chunksize=10 * 1024 * 1024)
                done = False
                while not done:
                    _, done = downloader.next_chunk()
            return dest_path
        except HttpError as e:
            raise RuntimeError(
                f"Failed to download file {file_id} to {dest_path}: {e}"
            ) from e

    def upload_file(
        self,
        local_path: Path,
        folder_id: str,
        mime_type: str | None = None,
        file_name: str | None = None,
    ) -> dict:
        """Upload a local file to a Drive folder (always resumable)."""
        if mime_type is None:
            mime_type, _ = mimetypes.guess_type(str(local_path))
            if mime_type is None:
                mime_type = "application/octet-stream"
        if file_name is None:
            file_name = local_path.name

        file_metadata = {"name": file_name, "parents": [folder_id]}
        media = MediaFileUpload(str(local_path), mimetype=mime_type, resumable=True)
        try:
            result = (
                self.service.files()
                .create(
                    body=file_metadata,
                    media_body=media,
                    fields="id, name, webViewLink",
                )
                .execute()
            )
            return result
        except HttpError as e:
            raise RuntimeError(
                f"Failed to upload {local_path} to folder {folder_id}: {e}"
            ) from e

    def find_or_create_folder(self, name: str, parent_folder_id: str) -> str:
        """Find an existing folder or create a new one. Returns folder ID."""
        q = (
            f"name='{name}' "
            f"and '{parent_folder_id}' in parents "
            f"and mimeType='application/vnd.google-apps.folder' "
            f"and trashed=false"
        )
        try:
            resp = (
                self.service.files()
                .list(q=q, fields="files(id)", pageSize=1)
                .execute()
            )
            files = resp.get("files", [])
            if files:
                return files[0]["id"]

            folder_metadata = {
                "name": name,
                "mimeType": "application/vnd.google-apps.folder",
                "parents": [parent_folder_id],
            }
            folder = (
                self.service.files()
                .create(body=folder_metadata, fields="id")
                .execute()
            )
            return folder["id"]
        except HttpError as e:
            raise RuntimeError(
                f"Failed to find or create folder '{name}' under {parent_folder_id}: {e}"
            ) from e

    def get_share_url(self, file_id: str) -> str:
        """Return the web view URL for a Drive file."""
        return f"https://drive.google.com/file/d/{file_id}/view"

    @staticmethod
    def pdf_mime() -> str:
        """Return the MIME type for PDF files."""
        return "application/pdf"

    @staticmethod
    def markdown_mime() -> str:
        """Return the MIME type for Markdown files."""
        return "text/markdown"
