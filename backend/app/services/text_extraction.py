"""Turn an uploaded file's raw bytes into page-tagged plain text.

Kept deliberately simple: two formats (PDF, plain text), no OCR, no layout
analysis. Each returned page is (page_number, text) — page_number is 1-indexed
and None for formats with no real page structure (plain text).
"""

import re
from typing import List, Optional, Tuple

Page = Tuple[Optional[int], str]


def _clean_text(text: str) -> str:
    """Collapse the whitespace noise PDF extraction tends to leave behind."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Collapse runs of 3+ blank lines down to one blank line, and trailing
    # spaces on each line, without touching intentional paragraph breaks.
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_pdf_pages(raw_bytes: bytes) -> List[Page]:
    """Extract text per page from a PDF using PyMuPDF."""
    import fitz  # PyMuPDF

    pages: List[Page] = []
    with fitz.open(stream=raw_bytes, filetype="pdf") as doc:
        for index, page in enumerate(doc):
            text = _clean_text(page.get_text())
            if text:
                pages.append((index + 1, text))
    return pages


def extract_txt_pages(raw_bytes: bytes) -> List[Page]:
    """Plain text has no pages — treat the whole file as one untagged page."""
    text = _clean_text(raw_bytes.decode("utf-8", errors="ignore"))
    return [(None, text)] if text else []


def extract_pages(filename: str, raw_bytes: bytes) -> List[Page]:
    """Dispatch on file extension. Falls back to plain-text decoding."""
    lower = (filename or "").lower()
    if lower.endswith(".pdf"):
        return extract_pdf_pages(raw_bytes)
    return extract_txt_pages(raw_bytes)
