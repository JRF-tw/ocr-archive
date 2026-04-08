#!/usr/bin/env python3
"""Add bookmarks to a PDF based on tagged.json for lawyer browsing.

Reads a tagged.json (output of tag_docs.py workflow) and annotates the original
PDF with a hierarchical bookmark tree organized by document category.

Bookmark hierarchy:
  [Category]
    └── doc_type｜parties｜date  →  page N

Categories (in order):
  行政文件  — 封面, 空白頁, 辦理事項表, 文書目錄, 書記官辦理事項表
  訴訟書狀  — 準備書狀, 起訴書, 辯護狀, etc.
  程序文件  — 送達證書, 閱卷聲請書, etc.
  其他      — anything else

Usage:
    python tools/tag_pdf.py <original_pdf> <tagged_json> [--output <out.pdf>]

Output:
    <stem>_bookmarked.pdf  (or path specified via --output)
"""

import argparse
import json
import sys
from pathlib import Path

import fitz  # PyMuPDF


# ── Category classification ────────────────────────────────────────────────────

ADMIN_TYPES = {
    "卷宗封面", "空白頁", "辦理事項表", "文書目錄",
    "第一二審法院刑事紀錄書記官應注意辦理事項表",
    "書記官辦理事項表",
}

PROCEDURAL_TYPES = {
    "送達證書", "閱卷聲請書", "通知書", "傳票", "收據",
}

CATEGORIES = ["行政文件", "訴訟書狀", "程序文件", "其他"]


def classify(doc_type: str) -> str:
    if doc_type in ADMIN_TYPES:
        return "行政文件"
    if doc_type in PROCEDURAL_TYPES:
        return "程序文件"
    # Heuristic: anything containing 狀/書/訴/辯 is a pleading
    if any(ch in doc_type for ch in ("狀", "書", "訴", "辯", "準備")):
        return "訴訟書狀"
    return "其他"


# ── Bookmark label ─────────────────────────────────────────────────────────────

def build_label(doc: dict) -> str:
    """Short human-readable label for the bookmark entry."""
    parts = [doc.get("doc_type") or "（未知）"]

    parties = doc.get("parties") or []
    if parties:
        # Show at most 2 parties to keep labels short
        party_str = "、".join(parties[:2])
        if len(parties) > 2:
            party_str += f" 等{len(parties)}人"
        parts.append(party_str)

    date = doc.get("date")
    if date:
        parts.append(date)

    return "｜".join(parts)


# ── Main ───────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Add bookmarks to PDF from tagged.json")
    parser.add_argument("pdf", help="Original PDF file path")
    parser.add_argument("tagged_json", help="tagged.json produced by tag_docs.py workflow")
    parser.add_argument("--output", help="Output PDF path (default: <stem>_bookmarked.pdf)")
    parser.add_argument("--page-offset", type=int, default=0,
                        help="Page offset: add this to start_page to get PDF page (default: 0)")
    args = parser.parse_args()

    pdf_path = Path(args.pdf)
    json_path = Path(args.tagged_json)

    for p in [pdf_path, json_path]:
        if not p.exists():
            print(f"ERROR: {p} not found", file=sys.stderr)
            sys.exit(1)

    output_path = Path(args.output) if args.output \
        else pdf_path.parent / f"{pdf_path.stem}_bookmarked.pdf"

    with json_path.open(encoding="utf-8") as f:
        data = json.load(f)

    documents = data.get("documents") or []
    if not documents:
        print("ERROR: No documents found in tagged JSON.", file=sys.stderr)
        sys.exit(1)

    # Group documents by category, preserving order within each category
    grouped: dict[str, list[dict]] = {cat: [] for cat in CATEGORIES}
    for doc in documents:
        cat = classify(doc.get("doc_type") or "")
        grouped[cat].append(doc)

    # Build PyMuPDF table of contents:
    # Each entry is [level, title, page_1indexed]
    toc: list[list] = []

    for cat in CATEGORIES:
        docs = grouped[cat]
        if not docs:
            continue
        # Category header (level 1) — points to first doc's start page
        first_page = docs[0]["start_page"] + args.page_offset
        toc.append([1, cat, first_page])

        for doc in docs:
            page = doc["start_page"] + args.page_offset
            label = build_label(doc)
            toc.append([2, label, page])

    # Open PDF, apply bookmarks, save
    pdf = fitz.open(str(pdf_path))
    pdf.set_toc(toc)
    pdf.save(str(output_path))
    pdf.close()

    print(f"Bookmarks added: {len(toc)} entries ({len(documents)} documents)")
    print(f"Output: {output_path}")


if __name__ == "__main__":
    main()
