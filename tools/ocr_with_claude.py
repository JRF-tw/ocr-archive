#!/usr/bin/env python3
"""OCR a PDF using Claude's vision capabilities.

Steps:
1. Convert each PDF page to a PNG image via pdftoppm
2. Send each image to Claude claude-opus-4-6 with an OCR prompt
3. Save per-page text + combined output
"""

import base64
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import anthropic

PDF_PATH = Path("references/example/input/高院刑事_106上訴3315卷2_P1-544_OCR_1_8.pdf")
OUTPUT_DIR = Path("references/example/input")
OUTPUT_JSON = OUTPUT_DIR / "ocr_claude_pages.json"
OUTPUT_TXT = OUTPUT_DIR / "ocr_claude_full.txt"

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
    """Convert a single PDF page to a base64-encoded PNG."""
    out_prefix = tmp_dir / f"page_{page_num:03d}"
    subprocess.run(
        [
            "pdftoppm",
            "-r", "200",          # 200 DPI — good balance of quality vs size
            "-png",
            "-f", str(page_num),
            "-l", str(page_num),
            str(pdf_path),
            str(out_prefix),
        ],
        check=True,
        capture_output=True,
    )
    # pdftoppm outputs: page_001-1.png (single page)
    imgs = list(tmp_dir.glob(f"page_{page_num:03d}*.png"))
    if not imgs:
        raise FileNotFoundError(f"No image generated for page {page_num}")
    img_path = imgs[0]
    return base64.standard_b64encode(img_path.read_bytes()).decode()


def ocr_page(client: anthropic.Anthropic, image_b64: str, page_num: int) -> str:
    """Send an image to Claude and return the transcribed text."""
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


def get_page_count(pdf_path: Path) -> int:
    result = subprocess.run(
        ["pdfinfo", str(pdf_path)], capture_output=True, text=True, check=True
    )
    for line in result.stdout.splitlines():
        if line.startswith("Pages:"):
            return int(line.split(":")[1].strip())
    raise RuntimeError("Could not determine page count")


def main():
    if not PDF_PATH.exists():
        print(f"ERROR: PDF not found at {PDF_PATH}")
        sys.exit(1)

    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env

    page_count = get_page_count(PDF_PATH)
    print(f"PDF has {page_count} pages")

    results = []

    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp = Path(tmp_dir)
        for page_num in range(1, page_count + 1):
            print(f"Page {page_num}/{page_count}:")
            try:
                image_b64 = pdf_page_to_base64(PDF_PATH, page_num, tmp)
                text = ocr_page(client, image_b64, page_num)
                results.append({"page": page_num, "text": text})
            except Exception as e:
                print(f"  ERROR: {e}")
                results.append({"page": page_num, "text": "", "error": str(e)})

    # Save per-page JSON
    OUTPUT_JSON.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\nSaved per-page JSON to {OUTPUT_JSON}")

    # Save combined text
    combined = "\n\n".join(
        f"=== Page {r['page']} ===\n{r['text']}" for r in results
    )
    OUTPUT_TXT.write_text(combined, encoding="utf-8")
    print(f"Saved combined text to {OUTPUT_TXT}")


if __name__ == "__main__":
    main()
