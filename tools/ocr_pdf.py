#!/usr/bin/env python3
"""OCR a PDF using Claude Code's built-in vision (no API key needed).

Converts the PDF to page images, then prints a ready-to-paste prompt
(loaded from a YAML file) for Claude Code to transcribe each page.

Usage:
    python tools/ocr_pdf.py <pdf_path> [options]

Options:
    --dpi INT          Resolution (default: 200)
    --out-dir DIR      Where to save images (default: <pdf_stem>_pages/ next to PDF)
    --pages A-B        Page range, e.g. 1-5 (default: all)
    --prompt YAML      Prompt YAML to use (default: tools/prompts/ocr_legal_tw.yaml)

Workflow:
    1. Run this script → generates page images + prints full prompt
    2. Copy the printed prompt and paste it into Claude Code
    3. Claude Code reads each image and saves the Markdown OCR result
"""

import argparse
import sys
from pathlib import Path

from tools._shared import load_prompt
from tools.pdf_to_images import convert


PROMPTS_DIR = Path(__file__).parent / "prompts"
DEFAULT_PROMPT = PROMPTS_DIR / "ocr_legal_tw.yaml"


def build_prompt(prompt_cfg: dict, pdf_name: str, n_pages: int, output_path: Path, images: list[Path]) -> str:
    instruction = prompt_cfg["instruction"].format(
        pdf_name=pdf_name,
        n_pages=n_pages,
        output_path=output_path,
    )
    image_list = "\n".join(str(p) for p in images)
    return f"{instruction}\n{image_list}"


def main():
    parser = argparse.ArgumentParser(description="Prepare PDF pages for Claude Code OCR")
    parser.add_argument("pdf", help="Path to input PDF")
    parser.add_argument("--dpi", type=int, default=200)
    parser.add_argument("--out-dir", help="Directory to save page images")
    parser.add_argument("--pages", help="Page range e.g. 1-5")
    parser.add_argument("--prompt", default=str(DEFAULT_PROMPT), help="Path to prompt YAML")
    args = parser.parse_args()

    pdf_path = Path(args.pdf).resolve()
    if not pdf_path.exists():
        print(f"ERROR: {pdf_path} not found", file=sys.stderr)
        sys.exit(1)

    prompt_path = Path(args.prompt)
    if not prompt_path.exists():
        print(f"ERROR: Prompt file not found: {prompt_path}", file=sys.stderr)
        sys.exit(1)

    out_dir = Path(args.out_dir) if args.out_dir else pdf_path.parent / f"{pdf_path.stem}_pages"
    output_md = pdf_path.parent / f"{pdf_path.stem}_ocr.md"

    first, last = 0, 0
    if args.pages:
        parts = args.pages.split("-")
        first = int(parts[0])
        last = int(parts[1]) if len(parts) > 1 else first

    images = convert(pdf_path, out_dir, args.dpi, first, last)
    if not images:
        print("ERROR: No images generated.", file=sys.stderr)
        sys.exit(1)

    prompt_cfg = load_prompt(prompt_path)
    prompt = build_prompt(prompt_cfg, pdf_path.name, len(images), output_md, images)

    print("\n" + "=" * 60)
    print("📋 複製以下內容貼到 Claude Code：")
    print("=" * 60 + "\n")
    print(prompt)
    print("\n" + "=" * 60)


if __name__ == "__main__":
    main()
