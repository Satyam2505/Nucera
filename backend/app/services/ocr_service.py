"""Optional, local OCR for scanned PDFs.

Nothing leaves the machine: the engine is RapidOCR (ONNX models bundled in the
pip package, run on the CPU). It is optional because it pulls in onnxruntime and
OpenCV; install it with `pip install -r requirements-ocr.txt`. Without it,
scanned pages are simply not readable and the upload says how to enable OCR.

`recognize_page` is the one seam the rest of the code uses, so tests can replace
it and the engine can be swapped without touching text extraction.
"""

import logging
from typing import List, Optional

from app.config import OCR_ENABLED, OCR_MIN_CONFIDENCE

logger = logging.getLogger(__name__)

_engine: Optional[object] = None
_import_failed = False


def ocr_available() -> bool:
    """Whether OCR can run: switched on (OCR_ENABLED) and the engine installed."""
    global _import_failed
    if not OCR_ENABLED or _import_failed:
        return False
    try:
        import rapidocr_onnxruntime  # noqa: F401
    except ImportError:
        _import_failed = True
        return False
    return True


def _get_engine():
    global _engine
    if _engine is None:
        from rapidocr_onnxruntime import RapidOCR

        _engine = RapidOCR()
    return _engine


def _reading_order(results: List) -> List[str]:
    """Text lines top to bottom, then left to right. RapidOCR returns boxes as four
    corner points; lines whose tops are within half a line's height of each other are
    treated as one row."""
    lines = []
    for box, text, confidence in results:
        if not text or float(confidence) < OCR_MIN_CONFIDENCE:
            continue
        top = min(point[1] for point in box)
        bottom = max(point[1] for point in box)
        left = min(point[0] for point in box)
        lines.append((top, bottom - top, left, text.strip()))
    lines.sort(key=lambda item: (round(item[0] / max(item[1] / 2, 1.0)), item[2]))
    return [text for _, _, _, text in lines if text]


def recognize_page(image) -> str:
    """The text found in one page image (a numpy array, height x width x channels).
    Empty if nothing legible was found."""
    results, _timing = _get_engine()(image)
    if not results:
        return ""
    return "\n".join(_reading_order(results))
