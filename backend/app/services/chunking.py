"""Split extracted text into retrieval-sized chunks.

No tokenizer dependency — token counts are approximated as ~4 characters
per token, which is a standard rule of thumb for English prose and good
enough for sizing chunks. Kept as plain functions (not a class) so the
strategy is easy to swap out later.
"""

import re
from dataclasses import dataclass
from typing import List, Optional, Tuple

CHARS_PER_TOKEN = 4
TARGET_TOKENS = 650  # middle of the requested 500-800 token range
MAX_CHARS = TARGET_TOKENS * CHARS_PER_TOKEN  # ~2600 chars
OVERLAP_RATIO = 0.15  # middle of the requested 10-20% overlap
OVERLAP_CHARS = int(MAX_CHARS * OVERLAP_RATIO)

_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?])\s+")


@dataclass
class ChunkPiece:
    text: str
    page_number: Optional[int]
    chunk_index: int


def _split_sentences(text: str) -> List[str]:
    """Cheap sentence splitter — paragraph breaks first, then punctuation.
    Good enough for lecture notes and textbook prose without a real NLP
    tokenizer.
    """
    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    sentences: List[str] = []
    for paragraph in paragraphs:
        parts = _SENTENCE_BOUNDARY.split(paragraph)
        sentences.extend(p.strip() for p in parts if p.strip())
    return sentences


def chunk_text(
    text: str,
    max_chars: int = MAX_CHARS,
    overlap_chars: int = OVERLAP_CHARS,
) -> List[str]:
    """Split text into ~max_chars chunks, breaking on sentence boundaries
    where possible, with a trailing overlap carried into the next chunk so
    context isn't lost right at the seam.
    """
    text = text.strip()
    if not text:
        return []

    sentences = _split_sentences(text) or [text]

    chunks: List[str] = []
    current = ""

    for sentence in sentences:
        # A single sentence longer than max_chars has no smaller boundary
        # to respect, so it gets hard-split.
        if len(sentence) > max_chars:
            if current:
                chunks.append(current.strip())
                current = ""
            for start in range(0, len(sentence), max_chars):
                chunks.append(sentence[start : start + max_chars].strip())
            continue

        candidate = f"{current} {sentence}".strip() if current else sentence
        if len(candidate) <= max_chars:
            current = candidate
            continue

        chunks.append(current.strip())
        tail = current[-overlap_chars:] if overlap_chars else ""
        current = f"{tail} {sentence}".strip() if tail else sentence

    if current.strip():
        chunks.append(current.strip())

    return chunks


def chunk_pages(
    pages: List[Tuple[Optional[int], str]],
    max_chars: int = MAX_CHARS,
    overlap_chars: int = OVERLAP_CHARS,
) -> List[ChunkPiece]:
    """Chunk each page independently — a chunk never spans two pages, so
    page attribution stays unambiguous — then number chunks sequentially
    across the whole document.
    """
    pieces: List[ChunkPiece] = []
    index = 0
    for page_number, page_text in pages:
        for chunk in chunk_text(page_text, max_chars=max_chars, overlap_chars=overlap_chars):
            pieces.append(ChunkPiece(text=chunk, page_number=page_number, chunk_index=index))
            index += 1
    return pieces
