#!/usr/bin/env python3
"""Export tagged.json to CSV for Google Sheets import.

Reads tagged.json (or merged_tagged.json) and writes a CSV matching the
archive schema defined in references/data_model/google_sheet.md.

URL columns (原始 PDF, OCR Google Doc, 標注 PDF) are left empty for manual fill.

Handles both old format (parties: [...]) and new format
(defendants/lawyers/judges/others as separate arrays).

Usage:
    python tools/export_sheet.py <tagged_json> [options]

Options:
    --case-no TEXT    案號 short form, e.g. "106上訴3315"
                      If omitted, derived from the first non-null case_no field
    --volume TEXT     卷別, e.g. "卷2" (optional)
    --output PATH     Output CSV path (default: <stem>_sheet.csv)
"""

import argparse
import csv
import json
import re
import sys
from pathlib import Path

COLUMNS = [
    "案號", "卷別", "卷內序號", "文件類型", "摘要", "日期", "罪名",
    "被告", "辯護人", "法官", "其他關係人",
    "起始頁", "結束頁",
    "原始 PDF", "OCR Google Doc", "標注 PDF",
    "備註",
]


def normalize_case_no(raw: str) -> str:
    """'106年度上訴字第3315號' → '106上訴3315'"""
    m = re.match(r"(\d+)年度(\S+?)字第(\d+)號", raw)
    return f"{m.group(1)}{m.group(2)}{m.group(3)}" if m else raw


def join(values: list) -> str:
    return ",".join(v for v in (values or []) if v)


def doc_to_row(doc: dict, case_no: str, volume: str) -> dict:
    # Party fields — handle both old and new format
    if "defendants" in doc:
        defendants = join(doc.get("defendants") or [])
        lawyers    = join(doc.get("lawyers") or [])
        judges     = join(doc.get("judges") or [])
        others     = join(doc.get("others") or [])
    else:
        # Old format: single parties list → put in 被告, leave others empty
        defendants = join(doc.get("parties") or [])
        lawyers = lawyers = judges = others = ""

    return {
        "案號":         case_no,
        "卷別":         volume,
        "卷內序號":     doc.get("id", ""),
        "文件類型":     doc.get("doc_type") or "",
        "摘要":         doc.get("summary") or "",
        "日期":         doc.get("date") or "",
        "罪名":         doc.get("charge") or "",
        "被告":         defendants,
        "辯護人":       lawyers,
        "法官":         judges,
        "其他關係人":   others,
        "起始頁":       doc.get("start_page", ""),
        "結束頁":       doc.get("end_page", ""),
        "原始 PDF":     "",
        "OCR Google Doc": "",
        "標注 PDF":     "",
        "備註":         doc.get("notes") or "",
    }


def derive_case_no(documents: list) -> str:
    for doc in documents:
        raw = doc.get("case_no")
        if raw:
            return normalize_case_no(raw)
    return ""


def main():
    parser = argparse.ArgumentParser(description="Export tagged.json to CSV for Google Sheets")
    parser.add_argument("tagged_json", help="Path to tagged.json or merged_tagged.json")
    parser.add_argument("--case-no", help="案號 short form, e.g. '106上訴3315'")
    parser.add_argument("--volume", default="", help="卷別, e.g. '卷2'")
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

    with output_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        for doc in documents:
            writer.writerow(doc_to_row(doc, case_no, args.volume))

    print(f"Exported {len(documents)} rows → {output_path}")
    if not args.case_no and case_no:
        print(f"  案號 derived: {case_no}")


if __name__ == "__main__":
    main()
