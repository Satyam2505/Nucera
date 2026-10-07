"""Turn an uploaded file's raw bytes into page-tagged plain text.

Kept deliberately simple: PDF (with optional local OCR for scanned pages), Word
(.docx), PowerPoint (.pptx) and plain text (.txt, .md); no layout analysis. Each
returned page is (page_number, text): page_number is 1-indexed for a PDF page or a
slide, and None for formats with no real page structure (plain text, Word).

Anything that cannot be turned into text is refused with an UploadRejected
carrying the HTTP status to answer with, so the route never ingests a file it
doesn't understand.
"""

import io
import logging
import os
import re
import zipfile
from typing import Callable, List, Optional, Tuple

from app.config import OCR_DPI, OCR_MAX_PAGES, OCR_MIN_TEXT_CHARS
from app.services import ocr_service

logger = logging.getLogger(__name__)

Page = Tuple[Optional[int], str]

TEXT_EXTENSIONS = (".txt", ".md")
OFFICE_EXTENSIONS = (".docx", ".pptx")
ALLOWED_EXTENSIONS = (".pdf",) + OFFICE_EXTENSIONS + TEXT_EXTENSIONS
PDF_MAGIC = b"%PDF-"
# The PDF spec allows a little junk before the header, so look near the start.
PDF_MAGIC_WINDOW = 1024
# .docx and .pptx are zip archives.
ZIP_MAGIC = b"PK\x03\x04"
# What a .docx / .pptx must contain, whatever else is in it.
OFFICE_REQUIRED_MEMBER = {".docx": "word/document.xml", ".pptx": "ppt/presentation.xml"}
OFFICE_NAME = {".docx": "Word document", ".pptx": "PowerPoint presentation"}
# A zip can claim to hold far more than its size suggests (a "zip bomb"). The upload
# limit bounds the compressed size, so bound what it may expand to as well.
MAX_UNCOMPRESSED_BYTES = 200 * 1024 * 1024

UNSUPPORTED_MESSAGE = "Upload a PDF, Word (.docx), PowerPoint (.pptx), .txt or .md file."
NO_OCR_MESSAGE = (
    "This looks like a scanned PDF: its pages are pictures with no text to read. "
    "Reading it needs OCR, which isn't installed here (pip install -r requirements-ocr.txt)."
)


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


# --- PDF (text layer, and OCR for scanned pages) ---------------------------------------------


def _page_image(page):
    """A page rendered to a numpy image for OCR."""
    import numpy as np

    pixmap = page.get_pixmap(dpi=OCR_DPI, alpha=False)
    return np.frombuffer(pixmap.samples, dtype=np.uint8).reshape(pixmap.height, pixmap.width, pixmap.n)


def extract_pdf_pages(
    raw_bytes: bytes,
    recognize: Optional[Callable] = None,
    ocr_enabled: Optional[bool] = None,
) -> List[Page]:
    """Extract text per page from a PDF using PyMuPDF.

    A page with (almost) no text that holds an image is a scan, and is read with
    OCR when it is available. `recognize` and `ocr_enabled` exist so tests can
    stand in for the engine; normally the installed one is used.
    """
    import fitz  # PyMuPDF

    recognize = recognize or ocr_service.recognize_page
    can_ocr = ocr_service.ocr_available() if ocr_enabled is None else ocr_enabled

    pages: List[Page] = []
    scanned: List[int] = []
    with fitz.open(stream=raw_bytes, filetype="pdf") as doc:
        text_by_index = {}
        for index, page in enumerate(doc):
            text = _clean_text(page.get_text())
            text_by_index[index] = text
            if len(text) < OCR_MIN_TEXT_CHARS and page.get_images():
                scanned.append(index)

        if scanned and not can_ocr and not any(text_by_index.values()):
            raise UploadRejected(422, NO_OCR_MESSAGE)
        if scanned and can_ocr and len(scanned) > OCR_MAX_PAGES:
            raise UploadRejected(
                413,
                f"This scanned PDF has {len(scanned)} pages to read with OCR, but one upload is "
                f"limited to {OCR_MAX_PAGES} (set OCR_MAX_PAGES to change it). Split the file and "
                "upload the parts.",
            )

        if scanned and can_ocr:
            for index in scanned:
                recognized = _clean_text(recognize(_page_image(doc[index])) or "")
                # Keep a text layer that exists but is short (a page number, a caption).
                text_by_index[index] = (text_by_index[index] + "\n\n" + recognized).strip()
            logger.info("Read %d scanned page(s) with OCR", len(scanned))

        for index in range(len(text_by_index)):
            if text_by_index[index]:
                pages.append((index + 1, text_by_index[index]))
    return pages


# --- Word and PowerPoint ------------------------------------------------------------------------------


def _open_office_zip(raw_bytes: bytes, extension: str) -> None:
    """Refuse a file that doesn't look like the Office format its extension claims,
    or that expands to an unreasonable size, before anything parses it."""
    name = OFFICE_NAME[extension]
    if not raw_bytes.startswith(ZIP_MAGIC):
        raise UploadRejected(
            415,
            f"This file has a {extension} extension but isn't a {name}. "
            "(Older .doc/.ppt files and password-protected files aren't supported.)",
        )
    try:
        with zipfile.ZipFile(io.BytesIO(raw_bytes)) as archive:
            members = archive.namelist()
            expanded = sum(info.file_size for info in archive.infolist())
    except zipfile.BadZipFile:
        raise UploadRejected(422, f"Couldn't read this {name}. It may be corrupted.")
    if OFFICE_REQUIRED_MEMBER[extension] not in members:
        raise UploadRejected(415, f"This file has a {extension} extension but isn't a {name}.")
    if expanded > MAX_UNCOMPRESSED_BYTES:
        raise UploadRejected(413, f"This {name} expands to too much data to process.")


def _docx_text(paragraph) -> str:
    return paragraph.text.strip()


def extract_docx_pages(raw_bytes: bytes) -> List[Page]:
    """The text of a Word document in reading order: paragraphs, and tables with each
    row on one line (cells separated by " | "). Word has no fixed pages, so the whole
    document is one untagged page."""
    from docx import Document
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    document = Document(io.BytesIO(raw_bytes))
    blocks: List[str] = []
    for child in document.element.body.iterchildren():
        tag = child.tag.rsplit("}", 1)[-1]
        if tag == "p":
            text = _docx_text(Paragraph(child, document))
            if text:
                blocks.append(text)
        elif tag == "tbl":
            rows = []
            for row in Table(child, document).rows:
                cells: List[str] = []
                for cell in row.cells:
                    text = " ".join(part for part in (p.text.strip() for p in cell.paragraphs) if part)
                    if text and (not cells or cells[-1] != text):  # merged cells repeat
                        cells.append(text)
                if cells:
                    rows.append(" | ".join(cells))
            if rows:
                blocks.append("\n".join(rows))
    text = _clean_text("\n\n".join(blocks))
    return [(None, text)] if text else []


def _shape_text(shape) -> List[str]:
    """Text of one slide shape: a text frame, a table, or (recursively) a group."""
    if shape.shape_type == 6:  # MSO_SHAPE_TYPE.GROUP
        found: List[str] = []
        for member in shape.shapes:
            found.extend(_shape_text(member))
        return found
    if getattr(shape, "has_table", False) and shape.has_table:
        rows = []
        for row in shape.table.rows:
            cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
            if cells:
                rows.append(" | ".join(cells))
        return ["\n".join(rows)] if rows else []
    if getattr(shape, "has_text_frame", False) and shape.has_text_frame:
        text = shape.text_frame.text.strip()
        return [text] if text else []
    return []


def extract_pptx_pages(raw_bytes: bytes) -> List[Page]:
    """One page per slide (page number = slide number): its title, text boxes and
    tables, then its speaker notes. Slides with no text are skipped."""
    from pptx import Presentation

    presentation = Presentation(io.BytesIO(raw_bytes))
    pages: List[Page] = []
    for number, slide in enumerate(presentation.slides, start=1):
        blocks: List[str] = []
        title = slide.shapes.title
        if title is not None and title.has_text_frame and title.text_frame.text.strip():
            blocks.append(title.text_frame.text.strip())
        for shape in slide.shapes:
            if title is not None and shape.shape_id == title.shape_id:
                continue
            blocks.extend(_shape_text(shape))
        if slide.has_notes_slide:
            notes = slide.notes_slide.notes_text_frame
            if notes is not None and notes.text.strip():
                blocks.append("Speaker notes: " + notes.text.strip())
        text = _clean_text("\n\n".join(blocks))
        if text:
            pages.append((number, text))
    return pages


# --- plain text, and the entry points --------------------------------------------------------------------


def extract_txt_pages(raw_bytes: bytes) -> List[Page]:
    """Plain text has no pages — treat the whole file as one untagged page."""
    text = _clean_text(raw_bytes.decode("utf-8", errors="ignore"))
    return [(None, text)] if text else []


def check_extension(filename: str) -> str:
    """The file's lower-cased extension, or a 415 if it isn't one we accept."""
    extension = os.path.splitext(filename or "")[1].lower()
    if extension not in ALLOWED_EXTENSIONS:
        shown = f"'{extension}'" if extension else "without an extension"
        raise UploadRejected(415, f"Unsupported file type {shown}. {UNSUPPORTED_MESSAGE}")
    return extension


def extract_pages(filename: str, raw_bytes: bytes) -> List[Page]:
    """Dispatch on file extension and return the pages' text.

    Raises UploadRejected for an unsupported extension (415), a file that isn't what
    its extension says (415), a file that can't be read (422), a scanned PDF when OCR
    isn't installed (422) or is over its page limit (413), or a file with no
    extractable text (422).
    """
    extension = check_extension(filename)

    if extension == ".pdf":
        if PDF_MAGIC not in raw_bytes[:PDF_MAGIC_WINDOW]:
            raise UploadRejected(415, "This file has a .pdf extension but isn't a PDF.")
        try:
            pages = extract_pdf_pages(raw_bytes)
        except UploadRejected:
            raise
        except Exception:
            logger.exception("Could not read PDF %r", filename)
            raise UploadRejected(
                422, "Couldn't read this PDF. It may be corrupted or password-protected."
            )
    elif extension in OFFICE_EXTENSIONS:
        _open_office_zip(raw_bytes, extension)
        try:
            pages = extract_docx_pages(raw_bytes) if extension == ".docx" else extract_pptx_pages(raw_bytes)
        except Exception:
            logger.exception("Could not read %s %r", extension, filename)
            raise UploadRejected(
                422, f"Couldn't read this {OFFICE_NAME[extension]}. It may be corrupted."
            )
    else:
        pages = extract_txt_pages(raw_bytes)

    if not pages:
        raise UploadRejected(422, "No text could be extracted from this file.")
    return pages
