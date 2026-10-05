"""Turn an uploaded file's raw bytes into page-tagged plain text.

Kept deliberately simple: PDF and plain text (.txt, .md), no OCR, no layout
analysis. Each returned page is (page_number, text) — page_number is 1-indexed
and None for formats with no real page structure (plain text).

Anything that cannot be turned into text is refused with an UploadRejected
carrying the HTTP status to answer with, so the route never ingests a file it
doesn't understand.
"""

import logging
import os
import re
from typing import List, Optional, Tuple

logger = logging.getLogger(__name__)

Page = Tuple[Optional[int], str]

TEXT_EXTENSIONS = (".txt", ".md")
ALLOWED_EXTENSIONS = (".pdf",) + TEXT_EXTENSIONS
PDF_MAGIC = b"%PDF-"
# The PDF spec allows a little junk before the header, so look near the start.
PDF_MAGIC_WINDOW = 1024


class UploadRejected(Exception):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


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


def check_extension(filename: str) -> str:
    """The file's lower-cased extension, or a 415 if it isn't one we accept."""
    extension = os.path.splitext(filename or "")[1].lower()
    if extension not in ALLOWED_EXTENSIONS:
        shown = f"'{extension}'" if extension else "without an extension"
        raise UploadRejected(
            415, f"Unsupported file type {shown}. Upload a PDF, .txt or .md file."
        )
    return extension


def extract_pages(filename: str, raw_bytes: bytes) -> List[Page]:
    """Dispatch on file extension and return the pages' text.

    Raises UploadRejected for an unsupported extension (415), a ".pdf" that
    isn't a PDF (415), a PDF that can't be read (422), or a file with no
    extractable text (422).
    """
    extension = check_extension(filename)

    if extension == ".pdf":
        if PDF_MAGIC not in raw_bytes[:PDF_MAGIC_WINDOW]:
            raise UploadRejected(415, "This file has a .pdf extension but isn't a PDF.")
        try:
            pages = extract_pdf_pages(raw_bytes)
        except Exception:
            logger.exception("Could not read PDF %r", filename)
            raise UploadRejected(
                422, "Couldn't read this PDF. It may be corrupted or password-protected."
            )
    else:
        pages = extract_txt_pages(raw_bytes)

    if not pages:
        raise UploadRejected(
            422,
            "No text could be extracted from this file. "
            "(Scanned PDFs need OCR, which isn't supported.)",
        )
    return pages
