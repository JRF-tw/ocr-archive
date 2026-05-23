#!/usr/bin/env python3
"""Export tagged.json to CSV for Google Sheets import — one row per PDF.

Reads tagged.json (or merged_tagged.json) and writes a single-row CSV
matching the archive schema (references/data_model/google_sheet.md).

The Drive連結 column is left empty; drive_pipeline upload back-fills it.

Usage:
    python tools/export_sheet.py <tagged_json> [options]

Options:
    --case-no TEXT    案號 short form, e.g. "106上訴3315"
                      If omitted, derived from the first non-null case_no field
    --volume TEXT     Kept for CLI compatibility; ignored in new single-row format
    --output PATH     Output CSV path (default: <stem>_sheet.csv)
"""

import argparse
import csv
import json
import re
import sys
from pathlib import Path

COLUMNS = [
    "案號",
    "收件日期",
    "文件日期",
    "文件類型",
    "寄件人",
    "收件人",
    "摘要",
    "疑似罪名",
    "Drive連結",
    "備註",
]

# Column letter for Drive連結 (used by drive_pipeline to back-fill the URL)
DRIVE_URL_COLUMN = "I"


def normalize_case_no(raw: str) -> str:
    """'106年度上訴字第3315號' → '106上訴3315'"""
    m = re.match(r"(\d+)年度(\S+?)字第(\d+)號", raw)
    return f"{m.group(1)}{m.group(2)}{m.group(3)}" if m else raw


def _unique(items: list) -> list:
    """Return items deduplicated, preserving order, dropping empty strings."""
    seen: set = set()
    out = []
    for x in items:
        if x and x not in seen:
            out.append(x)
            seen.add(x)
    return out


def derive_case_no(documents: list) -> str:
    for doc in documents:
        raw = doc.get("case_no")
        if raw:
            return normalize_case_no(str(raw))
    return ""


def _receive_date(documents: list) -> str:
    """Date of first envelope-type document, or first non-null date overall."""
    envelope_types = {"信封", "收文信封", "掛號信封"}
    for doc in documents:
        if doc.get("doc_type") in envelope_types and doc.get("date"):
            return doc["date"]
    for doc in documents:
        if doc.get("date"):
            return doc["date"]
    return ""


def pdf_to_row(documents: list, case_no: str) -> dict:
    """Collapse all documents in a PDF into a single Archive row."""
    receive_date = _receive_date(documents)

    all_dates = _unique([d.get("date") or "" for d in documents])
    doc_dates = "；".join(all_dates)

    types = _unique([d.get("doc_type") or "" for d in documents])
    doc_types = "、".join(types)

    # Prefer explicit sender/recipient fields; fall back to defendants+others for sender
    if any("sender" in d for d in documents):
        sender = "、".join(_unique([d.get("sender") or "" for d in documents if d.get("sender")]))
    else:
        people: list = []
        for doc in documents:
            if "defendants" in doc:
                people += doc.get("defendants") or []
                people += doc.get("others") or []
            else:
                people += doc.get("parties") or []
        sender = "、".join(_unique(people))

    recipient = "、".join(_unique([d.get("recipient") or "" for d in documents if d.get("recipient")]))

    summaries = [d.get("summary") or "" for d in documents if d.get("summary")]
    summary = "\n".join(summaries)

    charges = _unique([d.get("charge") or "" for d in documents if d.get("charge")])
    charge = "；".join(charges)

    notes_list = [d.get("notes") or "" for d in documents if d.get("notes")]
    notes = "\n".join(notes_list)

    return {
        "案號":     case_no,
        "收件日期": receive_date,
        "文件日期": doc_dates,
        "文件類型": doc_types,
        "寄件人":   sender,
        "收件人":   recipient,
        "摘要":     summary,
        "疑似罪名": charge,
        "Drive連結": "",
        "備註":     notes,
    }


def main():
    parser = argparse.ArgumentParser(description="Export tagged.json to single-row CSV for Google Sheets")
    parser.add_argument("tagged_json", help="Path to tagged.json or merged_tagged.json")
    parser.add_argument("--case-no", help="案號 short form, e.g. '106上訴3315'")
    parser.add_argument("--volume", default="", help="(kept for compatibility, not used in new format)")
    parser.add_argument("--output", help="Output CSV path (default: <stem>_sheet.csv)")
    args = parser.parse_args()

    json_path = Path(args.tagged_json)
    if not json_path.exists():
        print(f"ERROR: {json_path} not found", file=sys.stderr)
        sys.exit(1)

    with json_path.open(encoding="utf-8") as f:
        data = json.load(f)

    documents = data.get("documents") or []
    if not documents:
        print("ERROR: No documents found in JSON.", file=sys.stderr)
        sys.exit(1)

    case_no = args.case_no or derive_case_no(documents)
    output_path = Path(args.output) if args.output \
        else json_path.parent / f"{json_path.stem}_sheet.csv"

    row = pdf_to_row(documents, case_no)

    with output_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerow(row)

    print(f"Exported 1 row → {output_path}")
    if not args.case_no and case_no:
        print(f"  案號 derived: {case_no}")


if __name__ == "__main__":
    main()
