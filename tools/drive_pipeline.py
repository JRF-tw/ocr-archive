#!/usr/bin/env python3
"""Drive pipeline CLI — download from Drive, upload outputs, track state.

Subcommands:
    run FILE_ID       Download a PDF and create a work directory
    watch [--once]    Poll the Queue sheet for pending jobs
    upload WORK_DIR   Upload pipeline outputs to Drive
    status WORK_DIR   Print manifest status table
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

from tools import drive_manifest
from tools.drive_manifest import _utc_now_iso
from tools.google_drive_client import GoogleDriveClient
from tools.google_sheets_client import GoogleSheetsClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_config(args: argparse.Namespace) -> dict:
    """Load config from ~/.jrf/drive_config.json, overlay CLI flags."""
    config_path = Path(args.config_path)
    config: dict = {}
    if config_path.exists():
        with open(config_path, encoding="utf-8") as f:
            config = json.load(f)

    # CLI overrides
    for key in (
        "spreadsheet_id", "input_folder_id", "output_folder_id",
        "work_root", "queue_tab", "archive_tab",
    ):
        cli_val = getattr(args, key, None)
        if cli_val is not None:
            config[key] = cli_val

    # Defaults for optional keys
    config.setdefault("queue_tab", "Queue")
    config.setdefault("archive_tab", "Archive")
    config.setdefault("work_root", "./work")

    # Validate required keys
    required = ["spreadsheet_id", "input_folder_id", "output_folder_id"]
    missing = [k for k in required if not config.get(k)]
    if missing:
        print(
            f"ERROR: Missing required config keys: {', '.join(missing)}. "
            f"Set them in {config_path} or via CLI flags.",
            file=sys.stderr,
        )
        sys.exit(3)

    return config


def _build_clients(
    args: argparse.Namespace,
) -> tuple[GoogleDriveClient, GoogleSheetsClient]:
    """Build Drive and Sheets clients. Exits 3 on auth failure."""
    creds_path = Path(args.credentials_path)
    token_path = Path(args.token_path)
    try:
        drive = GoogleDriveClient(creds_path, token_path)
        sheets = GoogleSheetsClient(creds_path, token_path)
        return drive, sheets
    except Exception as e:
        print(f"ERROR: Authentication failed: {e}", file=sys.stderr)
        sys.exit(3)


def _derive_case_no(documents: list) -> str:
    """Extract first non-null case_no from tagged documents."""
    for doc in documents:
        raw = doc.get("case_no")
        if raw:
            return str(raw)
    return ""


def _upload_file_entry(
    manifest: dict,
    work_dir: Path,
    drive: GoogleDriveClient,
    key: str,
    file_path: Path | None,
    mime_type: str,
    folder_id: str,
    force: bool,
    not_found_error: str,
) -> bool:
    """Upload one manifest entry. Returns True if it failed."""
    if manifest.get("uploads", {}).get(key, {}).get("status") == "uploaded" and not force:
        return False
    if file_path is None or not file_path.exists():
        drive_manifest.mark_upload(manifest, key, "failed", error=not_found_error)
        drive_manifest.save(manifest, work_dir)
        return True
    try:
        result = drive.upload_file(file_path, folder_id, mime_type)
        url = drive.get_share_url(result["id"])
        drive_manifest.mark_upload(
            manifest, key, "uploaded",
            drive_file_id=result["id"], drive_url=url,
            uploaded_at=_utc_now_iso(), local_path=str(file_path),
        )
        drive_manifest.save(manifest, work_dir)
        return False
    except Exception as e:
        drive_manifest.mark_upload(manifest, key, "failed", error=str(e))
        drive_manifest.save(manifest, work_dir)
        return True


def _load_tagged_json(work_dir: Path) -> dict | None:
    """Load merged_tagged.json or first tagged.json found in a chunk subdirectory."""
    merged = work_dir / "merged_tagged.json"
    if merged.exists():
        with open(merged, encoding="utf-8") as f:
            return json.load(f)
    tagged_files = sorted(work_dir.glob("*/tagged.json"))
    if tagged_files:
        with open(tagged_files[0], encoding="utf-8") as f:
            return json.load(f)
    return None


def _run_ocr(pdf_path: Path, max_retries: int = 3, retry_wait: int = 70) -> int:
    """Run the OCR pipeline non-interactively via the claude CLI.

    Retries up to max_retries times with retry_wait second delay to recover
    from transient API rate-limit errors (429).
    """
    project_root = Path(__file__).parent.parent
    cmd = [
        "claude",
        "-p",
        f"/ocr-legal-pdf {pdf_path}",
        "--dangerously-skip-permissions",
    ]
    for attempt in range(1, max_retries + 1):
        result = subprocess.run(cmd, cwd=str(project_root))
        if result.returncode == 0:
            return 0
        if attempt < max_retries:
            print(
                f"  OCR attempt {attempt}/{max_retries} failed (exit {result.returncode}),"
                f" retrying in {retry_wait}s ..."
            )
            sys.stdout.flush()
            time.sleep(retry_wait)
    return result.returncode


# ---------------------------------------------------------------------------
# Subcommand: run
# ---------------------------------------------------------------------------

def _run_single(
    file_id: str,
    drive: GoogleDriveClient,
    sheets: GoogleSheetsClient,
    config: dict,
) -> tuple[int, Path | None]:
    """Download a single file from Drive, create work dir and manifest.

    Returns (0, work_dir) on success, (1, None) on failure.
    """
    spreadsheet_id = config["spreadsheet_id"]
    queue_tab = config["queue_tab"]
    work_root = Path(config["work_root"]).expanduser()

    try:
        metadata = drive.get_file_metadata(file_id)
    except Exception as e:
        print(f"ERROR: Failed to get metadata for {file_id}: {e}", file=sys.stderr)
        try:
            sheets.update_job_status(
                spreadsheet_id, queue_tab, file_id, "failed", error=str(e),
            )
        except Exception:
            pass
        return 1, None

    file_name = metadata["name"]
    pdf_stem = Path(file_name).stem
    work_dir = work_root / pdf_stem
    work_dir.mkdir(parents=True, exist_ok=True)

    # Update Queue to running BEFORE download (EC-3)
    try:
        sheets.update_job_status(
            spreadsheet_id, queue_tab, file_id, "running",
            started_at=_utc_now_iso(), work_dir=str(work_dir.resolve()),
        )
    except Exception as e:
        print(f"WARNING: Failed to update Queue to running: {e}", file=sys.stderr)

    # Init manifest and populate input (EC-1: save after input populated)
    manifest = drive_manifest.load(work_dir)
    manifest["input"]["file_id"] = file_id
    manifest["input"]["file_name"] = file_name
    manifest["input"]["folder_id"] = metadata.get("parents", [None])[0] if "parents" in metadata else None
    manifest["input"]["md5_checksum"] = metadata.get("md5Checksum")
    manifest["input"]["local_pdf_path"] = str(work_dir / file_name)
    drive_manifest.save(manifest, work_dir)

    # Download file (EC-1: save after download)
    try:
        drive.download_file(file_id, work_dir / file_name)
        manifest["input"]["downloaded_at"] = _utc_now_iso()
        drive_manifest.save(manifest, work_dir)
    except Exception as e:
        manifest["input"]["downloaded_at"] = None
        drive_manifest.save(manifest, work_dir)
        print(f"ERROR: Download failed for {file_id}: {e}", file=sys.stderr)
        try:
            sheets.update_job_status(
                spreadsheet_id, queue_tab, file_id, "failed", error=str(e),
            )
        except Exception:
            pass
        return 1, None

    return 0, work_dir


def cmd_run(args: argparse.Namespace) -> int:
    config = _load_config(args)
    drive, sheets = _build_clients(args)
    exit_code, work_dir = _run_single(args.file_id, drive, sheets, config)
    if work_dir is not None:
        print(str(work_dir.resolve()))
    return exit_code


# ---------------------------------------------------------------------------
# Subcommand: watch
# ---------------------------------------------------------------------------

def cmd_watch(args: argparse.Namespace) -> int:
    config = _load_config(args)
    drive, sheets = _build_clients(args)
    spreadsheet_id = config["spreadsheet_id"]
    queue_tab = config["queue_tab"]

    queue_headers = [
        "file_id", "file_name", "status",
        "enqueued_at", "started_at", "completed_at", "work_dir", "error",
    ]
    try:
        sheets.ensure_tab(spreadsheet_id, queue_tab, queue_headers)
    except Exception as e:
        print(f"WARNING: Could not ensure Queue tab headers: {e}", file=sys.stderr)

    while True:
        try:
            pending = sheets.get_pending_jobs(spreadsheet_id, queue_tab)
        except Exception as e:
            print(f"ERROR: Failed to poll queue: {e}", file=sys.stderr)
            if args.once:
                return 1
            time.sleep(args.interval)
            continue

        any_failed = False
        for job in pending:
            fid = job.get("file_id")
            fname = job.get("file_name", fid or "unknown")
            if not fid:
                continue

            started_ts = _utc_now_iso()
            print(f"\n{'=' * 60}")
            print(f"  File:    {fname}")
            print(f"  ID:      {fid}")
            print(f"  Started: {started_ts}")
            print(f"  [1/3] Downloading from Drive ...")
            sys.stdout.flush()

            exit_code, work_dir = _run_single(fid, drive, sheets, config)
            if exit_code != 0 or work_dir is None:
                print(f"  FAILED at step 1/3 (download)")
                any_failed = True
                continue

            pdf_path = work_dir / fname
            print(f"  [2/3] Running OCR pipeline ...")
            sys.stdout.flush()

            ocr_rc = _run_ocr(pdf_path)
            if ocr_rc != 0:
                print(f"  FAILED at step 2/3 (OCR), exit code {ocr_rc}")
                any_failed = True
                try:
                    sheets.update_job_status(
                        spreadsheet_id, queue_tab, fid, "failed",
                        error=f"OCR failed with exit code {ocr_rc}",
                    )
                except Exception:
                    pass
                continue

            print(f"  [3/3] Uploading outputs to Drive ...")
            sys.stdout.flush()

            upload_args = argparse.Namespace(**vars(args))
            upload_args.work_dir = str(work_dir)
            upload_args.force = False
            upload_rc = cmd_upload(upload_args)
            if upload_rc != 0:
                print(f"  FAILED at step 3/3 (upload), exit code {upload_rc}")
                any_failed = True
                continue

            try:
                drive.trash_file(fid)
                print(f"  已從 INPUT 移除：{fname}")
            except Exception as e:
                print(f"  WARNING: 無法移除 INPUT 檔案：{e}", file=sys.stderr)

            completed_ts = _utc_now_iso()
            print(f"  Completed: {completed_ts}")
            print(f"{'=' * 60}")

        if args.once:
            return 1 if any_failed else 0

        time.sleep(args.interval)


# ---------------------------------------------------------------------------
# Subcommand: upload
# ---------------------------------------------------------------------------

def cmd_upload(args: argparse.Namespace) -> int:
    config = _load_config(args)
    drive, sheets = _build_clients(args)
    work_dir = Path(args.work_dir).resolve()
    force = args.force

    manifest = drive_manifest.load(work_dir)
    spreadsheet_id = config["spreadsheet_id"]
    archive_tab = config["archive_tab"]
    queue_tab = config["queue_tab"]
    output_folder_id = config["output_folder_id"]

    file_id = manifest.get("input", {}).get("file_id")
    file_name = manifest.get("input", {}).get("file_name", "")
    pdf_stem = Path(file_name).stem if file_name else work_dir.name

    # --- Extract case_no and volume ---
    tagged_data = _load_tagged_json(work_dir)
    documents = tagged_data.get("documents", []) if tagged_data else []
    case_no = _derive_case_no(documents) if documents else ""
    if not case_no:
        case_no = pdf_stem

    volume = ""
    if documents:
        for doc in documents:
            v = doc.get("卷別", "")
            if v:
                volume = str(v)
                break

    # --- Create Drive subfolders ---
    try:
        case_folder = drive.find_or_create_folder(case_no, output_folder_id)
        subfolder_name = f"{volume}_{pdf_stem}" if volume else pdf_stem
        sub_folder = drive.find_or_create_folder(subfolder_name, case_folder)
        manifest["output_folder_id"] = sub_folder
        drive_manifest.save(manifest, work_dir)
    except Exception as e:
        print(f"ERROR: Failed to create Drive folders: {e}", file=sys.stderr)
        return 2

    any_failed = False

    # --- 1. Upload bookmarked PDF ---
    bm_files = sorted(work_dir.glob("*_bookmarked.pdf"))
    any_failed |= _upload_file_entry(
        manifest, work_dir, drive,
        drive_manifest.BOOKMARKED_PDF,
        bm_files[0] if bm_files else None,
        "application/pdf", sub_folder, force,
        "No *_bookmarked.pdf found in work directory",
    )

    # --- 2. Upload OCR markdown ---
    ocr_path: Path | None = work_dir / "merged_ocr.md"
    if not ocr_path.exists():
        chunks = sorted(work_dir.glob("*/ocr_corrected.md"))
        ocr_path = chunks[0] if chunks else None
    any_failed |= _upload_file_entry(
        manifest, work_dir, drive,
        drive_manifest.OCR_MARKDOWN,
        ocr_path,
        "text/markdown", sub_folder, force,
        "No merged_ocr.md or */ocr_corrected.md found",
    )

    # --- 3. Append CSV to Archive sheet ---
    sr_status = manifest.get("uploads", {}).get(drive_manifest.SHEET_ROWS, {}).get("status")
    if sr_status == "appended" and not force:
        pass  # skip
    else:
        csv_files = sorted(work_dir.glob("*_sheet.csv"))
        if csv_files:
            csv_path = csv_files[0]
            try:
                sheets.ensure_tab(spreadsheet_id, archive_tab)

                all_data = (
                    sheets.service.spreadsheets()
                    .values()
                    .get(spreadsheetId=spreadsheet_id, range=archive_tab)
                    .execute()
                )
                old_row_count = len(all_data.get("values", []))

                rows_appended = sheets.append_from_csv(
                    spreadsheet_id, archive_tab, csv_path,
                )
                drive_manifest.mark_upload(
                    manifest, drive_manifest.SHEET_ROWS, "appended",
                    local_csv_path=str(csv_path),
                    spreadsheet_id=spreadsheet_id,
                    spreadsheet_url=GoogleSheetsClient.get_spreadsheet_url(spreadsheet_id),
                    tab_name=archive_tab,
                    rows_appended=rows_appended,
                    appended_at=_utc_now_iso(),
                )
                drive_manifest.save(manifest, work_dir)

                # --- 4. Back-fill URL columns in one batch call ---
                original_pdf_url = drive.get_share_url(file_id) if file_id else ""
                bookmarked_url = manifest["uploads"][drive_manifest.BOOKMARKED_PDF].get("drive_url") or ""
                ocr_url = manifest["uploads"][drive_manifest.OCR_MARKDOWN].get("drive_url") or ""

                url_updates = []
                for row_num in range(old_row_count + 1, old_row_count + 1 + rows_appended):
                    url_updates.extend([
                        {"range": f"{archive_tab}!N{row_num}", "values": [[original_pdf_url]]},
                        {"range": f"{archive_tab}!O{row_num}", "values": [[ocr_url]]},
                        {"range": f"{archive_tab}!P{row_num}", "values": [[bookmarked_url]]},
                    ])
                if url_updates:
                    try:
                        sheets.batch_update_cells(spreadsheet_id, url_updates)
                    except Exception as e:
                        print(f"WARNING: Failed to back-fill URLs: {e}", file=sys.stderr)

            except Exception as e:
                drive_manifest.mark_upload(
                    manifest, drive_manifest.SHEET_ROWS, "failed", error=str(e),
                )
                drive_manifest.save(manifest, work_dir)
                any_failed = True
        else:
            drive_manifest.mark_upload(
                manifest, drive_manifest.SHEET_ROWS, "failed",
                error="No *_sheet.csv found in work directory",
            )
            drive_manifest.save(manifest, work_dir)
            any_failed = True

    # --- Update Queue row ---
    if file_id:
        try:
            if any_failed:
                sheets.update_job_status(
                    spreadsheet_id, queue_tab, file_id, "failed",
                    error="One or more uploads failed",
                )
            else:
                manifest["pipeline_status"] = "complete"
                drive_manifest.save(manifest, work_dir)
                sheets.update_job_status(
                    spreadsheet_id, queue_tab, file_id, "done",
                    completed_at=_utc_now_iso(),
                )
        except Exception as e:
            print(f"WARNING: Failed to update Queue row: {e}", file=sys.stderr)

    return 2 if any_failed else 0


# ---------------------------------------------------------------------------
# Subcommand: status
# ---------------------------------------------------------------------------

def cmd_status(args: argparse.Namespace) -> int:
    work_dir = Path(args.work_dir).resolve()
    manifest = drive_manifest.load(work_dir)

    inp = manifest.get("input", {})
    print("=== Drive Pipeline Status ===")
    print(f"  Work dir:        {work_dir}")
    print(f"  File name:       {inp.get('file_name', 'N/A')}")
    print(f"  File ID:         {inp.get('file_id', 'N/A')}")
    print(f"  Downloaded at:   {inp.get('downloaded_at', 'N/A')}")
    print(f"  Pipeline status: {manifest.get('pipeline_status', 'N/A')}")
    print()

    uploads = manifest.get("uploads", {})
    print("=== Upload Status ===")
    for key in (drive_manifest.BOOKMARKED_PDF, drive_manifest.OCR_MARKDOWN, drive_manifest.SHEET_ROWS):
        entry = uploads.get(key, {})
        status = entry.get("status", "N/A")
        url = entry.get("drive_url") or entry.get("spreadsheet_url") or ""
        local = entry.get("local_path") or entry.get("local_csv_path") or ""
        error = entry.get("error") or ""
        print(f"  {key}:")
        print(f"    Status:     {status}")
        if url:
            print(f"    Drive URL:  {url}")
        if local:
            print(f"    Local path: {local}")
        if error:
            print(f"    Error:      {error}")
    print()

    return 0


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="drive_pipeline",
        description="Google Drive pipeline CLI for the JRF OCR workflow",
    )

    # Global flags
    parser.add_argument(
        "--config-path",
        default=str(Path.home() / ".jrf" / "drive_config.json"),
        help="Path to drive_config.json (default: ~/.jrf/drive_config.json)",
    )
    parser.add_argument(
        "--credentials-path",
        default=str(Path.home() / ".jrf" / "credentials.json"),
        help="Path to OAuth credentials (default: ~/.jrf/credentials.json)",
    )
    parser.add_argument(
        "--token-path",
        default=str(Path.home() / ".jrf" / "token.json"),
        help="Path to OAuth token (default: ~/.jrf/token.json)",
    )
    parser.add_argument("--spreadsheet-id", dest="spreadsheet_id")
    parser.add_argument("--input-folder-id", dest="input_folder_id")
    parser.add_argument("--output-folder-id", dest="output_folder_id")
    parser.add_argument("--work-root", dest="work_root")
    parser.add_argument("--queue-tab", dest="queue_tab")
    parser.add_argument("--archive-tab", dest="archive_tab")

    subs = parser.add_subparsers(dest="command", required=True)

    # run
    p_run = subs.add_parser("run", help="Download a PDF by file ID")
    p_run.add_argument("file_id", help="Google Drive file ID")
    p_run.set_defaults(func=cmd_run)

    # watch
    p_watch = subs.add_parser("watch", help="Poll Queue sheet for pending jobs")
    p_watch.add_argument(
        "--once", action="store_true",
        help="Process all pending jobs then exit",
    )
    p_watch.add_argument(
        "--interval", type=int, default=60,
        help="Polling interval in seconds (default: 60)",
    )
    p_watch.set_defaults(func=cmd_watch)

    # upload
    p_upload = subs.add_parser("upload", help="Upload pipeline outputs to Drive")
    p_upload.add_argument("work_dir", help="Path to work directory")
    p_upload.add_argument(
        "--force", action="store_true",
        help="Re-upload even if already uploaded/appended",
    )
    p_upload.set_defaults(func=cmd_upload)

    # status
    p_status = subs.add_parser("status", help="Print manifest status table")
    p_status.add_argument("work_dir", help="Path to work directory")
    p_status.set_defaults(func=cmd_status)

    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    exit_code = args.func(args)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
