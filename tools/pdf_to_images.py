#!/usr/bin/env python3
"""Convert a PDF to per-page PNG images for OCR.

Usage:
    python tools/pdf_to_images.py <pdf_path> [options]

Options:
    --dpi INT        Resolution in DPI (default: 200)
    --out-dir DIR    Output directory (default: <pdf_stem>_pages/ next to PDF)
    --pages A-B      Page range, e.g. 1-5 (default: all)

Output:
    <out_dir>/page_001.png, page_002.png, ...

Example:
    python tools/pdf_to_images.py references/example/input/foo.pdf
    python tools/pdf_to_images.py references/example/input/foo.pdf --dpi 300 --pages 1-10
"""

import argparse
import subprocess
import sys
from pathlib import Path


def convert(pdf_path: Path, out_dir: Path, dpi: int, first: int, last: int) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    prefix = out_dir / "page"

    cmd = ["pdftoppm", "-r", str(dpi), "-png"]
    if first:
        cmd += ["-f", str(first)]
    if last:
        cmd += ["-l", str(last)]
    cmd += [str(pdf_path), str(prefix)]

    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"ERROR: pdftoppm failed:\n{result.stderr}", file=sys.stderr)
        sys.exit(1)

    images = sorted(out_dir.glob("page*.png"))
    return images


def page_count(pdf_path: Path) -> int:
    result = subprocess.run(["pdfinfo", str(pdf_path)], capture_output=True, text=True)
    for line in result.stdout.splitlines():
        if line.startswith("Pages:"):
            return int(line.split(":")[1].strip())
    return 0


def main():
    parser = argparse.ArgumentParser(description="Convert PDF pages to PNG images")
    parser.add_argument("pdf", help="Path to input PDF")
    parser.add_argument("--dpi", type=int, default=200, help="Resolution (default: 200)")
    parser.add_argument("--out-dir", help="Output directory (default: <pdf_stem>_pages/ next to PDF)")
    parser.add_argument("--pages", help="Page range e.g. 1-5 (default: all)")
    args = parser.parse_args()

    pdf_path = Path(args.pdf).resolve()
    if not pdf_path.exists():
        print(f"ERROR: File not found: {pdf_path}", file=sys.stderr)
        sys.exit(1)

    out_dir = Path(args.out_dir) if args.out_dir else pdf_path.parent / f"{pdf_path.stem}_pages"

    first, last = 0, 0
    if args.pages:
        parts = args.pages.split("-")
        first = int(parts[0])
        last = int(parts[1]) if len(parts) > 1 else first

    total = page_count(pdf_path)
    print(f"PDF: {pdf_path.name}  ({total} pages)")
    print(f"Output: {out_dir}/")
    print(f"DPI: {args.dpi}")

    images = convert(pdf_path, out_dir, args.dpi, first, last)
    print(f"Generated {len(images)} image(s):")
    for img in images:
        print(f"  {img}")


if __name__ == "__main__":
    main()
