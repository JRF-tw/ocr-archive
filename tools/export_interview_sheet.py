#!/usr/bin/env python3
"""Export interview/interrogation records from tagged.json to CSV.

One row per person per session. Matches the 訊問筆錄索引 schema:
  卷別、頁數、筆錄、姓名、身份、備註

Usage:
    python tools/export_interview_sheet.py <tagged_json> [options]

Options:
    --volume TEXT    卷別 (e.g. "80重訴23")
    --output PATH    Output CSV path (default: <stem>_interview_sheet.csv)
"""

import argparse
import csv
import json
import re
import sys
from pathlib import Path

COLUMNS = ["卷別", "頁數", "筆錄", "姓名", "身份", "備註"]

# 筆錄類文件類型
INTERVIEW_TYPES = {
    "訊問筆錄", "偵訊筆錄", "詢問筆錄", "勘驗筆錄",
    "警詢筆錄", "偵查筆錄", "審判筆錄", "筆錄",
}

# 身份對應
ROLE_MAP = {
    "defendants": "被告",
    "others":     None,   # 從文件內容判斷
    "judges":     "法官",
    "lawyers":    "辯護人",
}


def iso_to_roc(date_str: str) -> str:
    """Convert ISO date to ROC format: 1991-11-22 → 80.11.22"""
    if not date_str:
        return ""
    try:
        parts = date_str.split("-")
        roc_year = int(parts[0]) - 1911
        return f"{roc_year}.{parts[1]}.{parts[2]}"
    except Exception:
        return date_str


def derive_volume(documents: list, cli_volume: str) -> str:
    """Get 卷別 from CLI or first document's case_no."""
    if cli_volume:
        return cli_volume
    for doc in documents:
        cn = doc.get("case_no")
        if cn:
            # Try to extract short form like "80重訴23"
            m = re.match(r"(\d+)年度(\S+?)字第(\d+)號", cn)
            if m:
                return f"{int(m.group(1))}{m.group(2)}{m.group(3)}"
            return cn
    return ""


def page_range(doc: dict) -> str:
    start = doc.get("start_page")
    end = doc.get("end_page")
    if start and end and start != end:
        return f"{start}-{end}"
    return str(start) if start else ""


def interview_type(doc: dict) -> str:
    """Build 筆錄 column: e.g. '訊問筆錄 80.11.22'"""
    doc_type = doc.get("doc_type") or "筆錄"
    date_roc = iso_to_roc(doc.get("date") or "")
    if date_roc:
        return f"{doc_type} {date_roc}"
    return doc_type


def expand_doc_to_rows(doc: dict, volume: str) -> list[dict]:
    """Expand one document into one row per person."""
    rows = []
    pages = page_range(doc)
    interview = interview_type(doc)

    # Collect all people with their roles
    people = []

    # Defendants
    for name in (doc.get("defendants") or []):
        if name:
            people.append((name, "被告"))

    # Others — try to infer role from summary/notes
    summary = (doc.get("summary") or "").lower()
    notes = (doc.get("notes") or "").lower()
    for name in (doc.get("others") or []):
        if not name:
            continue
        # Infer role
        if "告訴人" in summary or "告訴人" in notes:
            role = "告訴人"
        elif "被害人" in summary or "被害人" in notes:
            role = "被害人"
        elif "證人" in summary or "證人" in notes:
            role = "證人"
        elif "檢察官" in summary or "檢察官" in notes:
            role = "檢察官"
        else:
            role = "證人"  # default for others in interview context
        people.append((name, role))

    # Lawyers
    for name in (doc.get("lawyers") or []):
        if name:
            people.append((name, "辯護人"))

    # If no people found, still emit one row
    if not people:
        rows.append({
            "卷別": volume,
            "頁數": pages,
            "筆錄": interview,
            "姓名": "",
            "身份": "",
            "備註": doc.get("notes") or "",
        })
    else:
        for name, role in people:
            rows.append({
                "卷別": volume,
                "頁數": pages,
                "筆錄": interview,
                "姓名": name,
                "身份": role,
                "備註": doc.get("notes") or "",
            })

    return rows


def main():
    parser = argparse.ArgumentParser(description="Export interview records to CSV")
    parser.add_argument("tagged_json", help="Path to tagged.json or merged_tagged.json")
    parser.add_argument("--volume", default="", help="卷別 (e.g. '80重訴23')")
    parser.add_argument("--output", help="Output CSV path")
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

    volume = derive_volume(documents, args.volume)
    output_path = Path(args.output) if args.output \
        else json_path.parent / f"{json_path.stem}_interview_sheet.csv"

    # Filter to interview-type documents only
    interview_docs = [
        d for d in documents
        if any(t in (d.get("doc_type") or "") for t in INTERVIEW_TYPES)
    ]

    if not interview_docs:
        print(f"找不到筆錄類文件（共 {len(documents)} 份文件）", file=sys.stderr)
        sys.exit(0)

    all_rows = []
    for doc in interview_docs:
        all_rows.extend(expand_doc_to_rows(doc, volume))

    with output_path.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(all_rows)

    print(f"匯出 {len(all_rows)} 行（來自 {len(interview_docs)} 份筆錄）→ {output_path}")


if __name__ == "__main__":
    main()
