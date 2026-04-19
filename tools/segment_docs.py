#!/usr/bin/env python3
"""Detect document boundaries in OCR Markdown.

Reads an OCR Markdown file (output of ocr_pdf.py workflow), prints a ready-to-paste
prompt for Claude Code to identify individual document segments within the case file.

Usage:
    python tools/segment_docs.py <ocr_markdown> [options]

Options:
    --prompt YAML      Prompt YAML (default: tools/prompts/segment_docs.yaml)
    --chunk-size INT   Max pages per chunk (default: 50; 0 = no chunking)
    --chunk N          Process only chunk N (1-based); omit to print all chunks

Output:
    Prints prompt(s) to paste into Claude Code.
    Claude Code should output JSON → save as <stem>_segments.json
    Then run: python tools/tag_docs.py <stem>_segments.json <ocr_markdown>
"""

import argparse
import sys
from pathlib import Path

from tools._shared import load_prompt, split_into_pages

PROMPTS_DIR = Path(__file__).parent / "prompts"
DEFAULT_PROMPT = PROMPTS_DIR / "segment_docs.yaml"


def build_chunks(pages: list[tuple[int, str]], chunk_size: int) -> list[list[tuple[int, str]]]:
    if chunk_size == 0:
        return [pages]
    return [pages[i:i + chunk_size] for i in range(0, len(pages), chunk_size)]


def render_prompt(cfg: dict, source: str, chunk: list[tuple[int, str]]) -> str:
    page_offset = chunk[0][0]
    n_pages = len(chunk)
    content = "\n\n".join(text for _, text in chunk)
    return cfg["instruction"].format(
        source=source,
        n_pages=n_pages,
        page_offset=page_offset,
        content=content,
    )


def main():
    parser = argparse.ArgumentParser(description="Prepare OCR Markdown for document segmentation")
    parser.add_argument("markdown", help="Path to OCR Markdown file")
    parser.add_argument("--prompt", default=str(DEFAULT_PROMPT))
    parser.add_argument("--chunk-size", type=int, default=50,
                        help="Max pages per chunk (0 = no chunking)")
    parser.add_argument("--chunk", type=int, default=None,
                        help="Print only chunk N (1-based); omit for all")
    args = parser.parse_args()

    md_path = Path(args.markdown)
    if not md_path.exists():
        print(f"ERROR: {md_path} not found", file=sys.stderr)
        sys.exit(1)

    prompt_path = Path(args.prompt)
    if not prompt_path.exists():
        print(f"ERROR: prompt file not found: {prompt_path}", file=sys.stderr)
        sys.exit(1)

    cfg = load_prompt(prompt_path)
    markdown = md_path.read_text(encoding="utf-8")
    pages = list(split_into_pages(markdown).items())

    if not pages:
        print("ERROR: No '## 第 N 頁' headers found in Markdown. Is this an OCR output file?",
              file=sys.stderr)
        sys.exit(1)

    chunks = build_chunks(pages, args.chunk_size)
    total_chunks = len(chunks)

    output_stem = md_path.stem.replace("_ocr", "")
    segments_out = md_path.parent / f"{output_stem}_segments.json"

    target_chunks = [chunks[args.chunk - 1]] if args.chunk else chunks

    for i, chunk in enumerate(target_chunks):
        chunk_num = (args.chunk or (i + 1))
        page_from = chunk[0][0]
        page_to = chunk[-1][0]

        print(f"\n{'=' * 60}")
        print(f"📋 Chunk {chunk_num}/{total_chunks}（第 {page_from}~{page_to} 頁）")
        print(f"   複製以下內容貼到 Claude Code：")
        print(f"{'=' * 60}\n")
        print(render_prompt(cfg, md_path.name, chunk))
        print(f"\n{'=' * 60}")
        print(f"💾 將 Claude Code 的 JSON 回應存到：{segments_out}")
        if total_chunks > 1:
            print(f"   （多個 chunk 的結果請合併後再執行 tag_docs.py）")
        print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
