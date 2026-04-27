#!/usr/bin/env python3
"""Tag each identified document segment with structured metadata.

Reads the segments JSON (output of segment_docs.py workflow) and the OCR Markdown,
then prints a ready-to-paste prompt for Claude Code to extract metadata for each document.

Usage:
    python tools/tag_docs.py <segments_json> <ocr_markdown> [options]

Options:
    --prompt YAML      Prompt YAML (default: tools/prompts/tag_docs.yaml)
    --batch-size INT   Segments per batch (default: 10)
    --batch N          Process only batch N (1-based); omit for all

Output:
    Prints prompt(s) to paste into Claude Code.
    Claude Code should output JSON → save as <stem>_tagged.json
"""

import argparse
import json
import sys
from pathlib import Path

from tools._shared import load_prompt, split_into_pages

PROMPTS_DIR = Path(__file__).parent / "prompts"
DEFAULT_PROMPT = PROMPTS_DIR / "tag_docs.yaml"


def extract_pages_for_segment(pages: dict[int, str], start: int, end: int) -> str:
    """Return concatenated markdown for pages start..end (inclusive)."""
    parts = []
    for p in range(start, end + 1):
        if p in pages:
            parts.append(pages[p])
    return "\n\n".join(parts)


def render_prompt(cfg: dict, source: str, content: str, segments: list[dict]) -> str:
    return cfg["instruction"].format(
        source=source,
        content=content,
        segments=json.dumps(segments, ensure_ascii=False, indent=2),
    )


def main():
    parser = argparse.ArgumentParser(description="Tag document segments with metadata")
    parser.add_argument("segments_json", help="Path to segments JSON file")
    parser.add_argument("markdown", help="Path to OCR Markdown file")
    parser.add_argument("--prompt", default=str(DEFAULT_PROMPT))
    parser.add_argument("--batch-size", type=int, default=10,
                        help="Number of segments per batch (default: 10)")
    parser.add_argument("--batch", type=int, default=None,
                        help="Process only batch N (1-based); omit for all")
    args = parser.parse_args()

    seg_path = Path(args.segments_json)
    md_path = Path(args.markdown)

    for p in [seg_path, md_path]:
        if not p.exists():
            print(f"ERROR: {p} not found", file=sys.stderr)
            sys.exit(1)

    prompt_path = Path(args.prompt)
    if not prompt_path.exists():
        print(f"ERROR: prompt file not found: {prompt_path}", file=sys.stderr)
        sys.exit(1)

    cfg = load_prompt(prompt_path)
    markdown = md_path.read_text(encoding="utf-8")
    pages = split_into_pages(markdown)

    with seg_path.open(encoding="utf-8") as f:
        seg_data = json.load(f)

    # Support both single-chunk {segments:[...]} and merged multi-chunk formats
    segments = seg_data.get("segments") or seg_data.get("documents", [])
    source = seg_data.get("source", md_path.name)

    if not segments:
        print("ERROR: No segments found in JSON.", file=sys.stderr)
        sys.exit(1)

    batch_size = args.batch_size
    batches = [segments[i:i + batch_size] for i in range(0, len(segments), batch_size)]
    total_batches = len(batches)

    output_stem = md_path.stem.replace("_ocr", "")
    tagged_out = md_path.parent / f"{output_stem}_tagged.json"

    target_batches = [(args.batch, batches[args.batch - 1])] if args.batch \
        else list(enumerate(batches, 1))

    for batch_num, batch in target_batches:
        all_start = min(s["start_page"] for s in batch)
        all_end = max(s["end_page"] for s in batch)
        content = extract_pages_for_segment(pages, all_start, all_end)

        print(f"\n{'=' * 60}")
        print(f"📋 Batch {batch_num}/{total_batches}")
        print(f"   Segments {batch[0]['id']}~{batch[-1]['id']} "
              f"（第 {all_start}~{all_end} 頁，共 {len(batch)} 份文件）")
        print(f"   複製以下內容貼到 Claude Code：")
        print(f"{'=' * 60}\n")
        print(render_prompt(cfg, source, content, batch))
        print(f"\n{'=' * 60}")
        print(f"💾 將 Claude Code 的 JSON 回應存到：{tagged_out}")
        if total_batches > 1:
            print(f"   （多個 batch 的 documents 陣列請合併）")
        print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
