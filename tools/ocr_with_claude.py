#!/usr/bin/env python3
"""OCR a PDF using Claude's vision capabilities.

Steps:
1. Convert each PDF page to a PNG image via pdftoppm
2. Send each image to Claude claude-opus-4-6 with an OCR prompt
3. Save per-page text + combined output

Usage:
    python tools/ocr_with_claude.py <pdf_path> [--output-dir DIR]
"""

import argparse
import base64
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import anthropic

from tools.pdf_to_images import page_count

SYSTEM_PROMPT = """\
You are an expert OCR assistant specializing in Traditional Chinese legal documents from Taiwan.
Your task is to accurately transcribe the text visible in the image.

Instructions:
- Transcribe ALL visible text faithfully, preserving the original layout as much as possible
- For Traditional Chinese text, output proper Unicode Traditional Chinese characters
- For any tables, preserve the structure using plain text formatting
- Include any numbers, dates, case references, and legal terminology exactly as shown
- If text is unclear or partially visible, make your best effort and indicate uncertainty with [?]
- Do NOT add commentary, explanations, or translations — output the transcribed text only
- Preserve paragraph breaks and significant whitespace
- Ignore watermarks (like 李之聖 at the edges) — these are access-control stamps, not document content
"""

OCR_PROMPT = "Please transcribe all the text in this document page image."


def pdf_page_to_base64(pdf_path: Path, page_num: int, tmp_dir: Path) -> str:
    out_prefix = tmp_dir / f"page_{page_num:03d}"
    subprocess.run(
        [
            "pdftoppm",
            "-r", "200",  # 200 DPI — good balance of quality vs size
            "-png",
            "-f", str(page_num),
            "-l", str(page_num),
            str(pdf_path),
            str(out_prefix),
        ],
        check=True,
        capture_output=True,
    )
    imgs = list(tmp_dir.glob(f"page_{page_num:03d}*.png"))
    if not imgs:
        raise FileNotFoundError(f"No image generated for page {page_num}")
    return base64.standard_b64encode(imgs[0].read_bytes()).decode()


def ocr_page(client: anthropic.Anthropic, image_b64: str, page_num: int) -> str:
    print(f"  Sending page {page_num} to Claude...", end=" ", flush=True)
    response = client.messages.create(
        model="claude-opus-4-6",
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {
                            "type": "base64",
                            "media_type": "image/png",
                            "data": image_b64,
                        },
                    },
                    {"type": "text", "text": OCR_PROMPT},
                ],
            }
        ],
    )
    text = response.content[0].text
    print(f"done ({len(text)} chars)")
    return text


def main():
    parser = argparse.ArgumentParser(description="OCR a PDF using Claude's vision capabilities")
    parser.add_argument("pdf", help="Path to input PDF")
    parser.add_argument("--output-dir", help="Output directory (default: same as PDF)")
    args = parser.parse_args()

    pdf_path = Path(args.pdf).resolve()
    if not pdf_path.exists():
        print(f"ERROR: PDF not found at {pdf_path}", file=sys.stderr)
        sys.exit(1)

    output_dir = Path(args.output_dir).resolve() if args.output_dir else pdf_path.parent
    output_dir.mkdir(parents=True, exist_ok=True)
    output_json = output_dir / f"{pdf_path.stem}_ocr_pages.json"
    output_txt = output_dir / f"{pdf_path.stem}_ocr_full.txt"

    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env

    n_pages = page_count(pdf_path)
    print(f"PDF has {n_pages} pages")

    results = []
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)
        for page_num in range(1, n_pages + 1):
            print(f"Page {page_num}/{n_pages}:")
            try:
                image_b64 = pdf_page_to_base64(pdf_path, page_num, tmp)
                text = ocr_page(client, image_b64, page_num)
                results.append({"page": page_num, "text": text})
            except Exception as e:
                print(f"  ERROR: {e}")
                results.append({"page": page_num, "text": "", "error": str(e)})

    output_json.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSaved per-page JSON to {output_json}")

    combined = "\n\n".join(f"=== Page {r['page']} ===\n{r['text']}" for r in results)
    output_txt.write_text(combined, encoding="utf-8")
    print(f"Saved combined text to {output_txt}")


if __name__ == "__main__":
    main()
