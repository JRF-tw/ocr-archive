"""Drive manifest management for tracking upload state."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

MANIFEST_FILE = "drive_manifest.json"


def _utc_now_iso() -> str:
    """Return current UTC time as ISO 8601 string."""
    return datetime.now(timezone.utc).isoformat()


def _empty_upload_entry() -> dict:
    """Return a blank upload entry with all fields set to None/pending."""
    return {
        "status": "pending",
        "local_path": None,
        "drive_file_id": None,
        "drive_url": None,
        "uploaded_at": None,
        "error": None,
    }


def _empty_sheet_entry() -> dict:
    """Return a blank sheet_rows upload entry."""
    return {
        "status": "pending",
        "local_csv_path": None,
        "spreadsheet_id": None,
        "spreadsheet_url": None,
        "tab_name": "Archive",
        "rows_appended": None,
        "appended_at": None,
        "error": None,
    }


def load(work_dir: Path) -> dict:
    """Load manifest from work_dir, or return an empty skeleton if not found."""
    manifest_path = work_dir / MANIFEST_FILE
    if manifest_path.exists():
        with open(manifest_path, encoding="utf-8") as f:
            return json.load(f)

    now = _utc_now_iso()
    return {
        "_schema_version": "1",
        "input": {
            "file_id": None,
            "file_name": None,
            "folder_id": None,
            "downloaded_at": None,
            "local_pdf_path": None,
            "md5_checksum": None,
        },
        "output_folder_id": None,
        "pipeline_status": None,
        "uploads": {
            "bookmarked_pdf": _empty_upload_entry(),
            "ocr_markdown": _empty_upload_entry(),
            "sheet_rows": _empty_sheet_entry(),
        },
        "created_at": now,
        "updated_at": now,
    }


def save(manifest: dict, work_dir: Path) -> None:
    """Atomically save manifest to work_dir (write tmp then os.replace)."""
    manifest["updated_at"] = _utc_now_iso()
    final_path = work_dir / MANIFEST_FILE
    tmp_path = work_dir / (MANIFEST_FILE + ".tmp")
    with open(tmp_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(tmp_path, final_path)


def mark_upload(manifest: dict, key: str, status: str, **fields) -> dict:
    """Update the status and extra fields for an upload entry. Mutates in-place."""
    entry = manifest["uploads"][key]
    entry["status"] = status
    for k, v in fields.items():
        entry[k] = v
    manifest["updated_at"] = _utc_now_iso()
    return manifest
