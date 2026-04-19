from __future__ import annotations

import re
from pathlib import Path

import yaml

PAGE_HEADER_RE = re.compile(r"^##\s+第\s*(\d+)\s*頁", re.MULTILINE)


def load_prompt(yaml_path: Path) -> dict:
    with yaml_path.open(encoding="utf-8") as f:
        return yaml.safe_load(f)


def split_into_pages(markdown: str) -> dict[int, str]:
    """Return {page_number: page_content} parsed from OCR markdown headers."""
    pages: dict[int, str] = {}
    matches = list(PAGE_HEADER_RE.finditer(markdown))
    for i, m in enumerate(matches):
        page_num = int(m.group(1))
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(markdown)
        pages[page_num] = markdown[start:end].strip()
    return pages
