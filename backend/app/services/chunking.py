"""Split extracted text into retrieval-sized chunks.

Chunks are sized for the embedding model, not for the LLM: the model that
turns a chunk into a search vector (all-MiniLM-L6-v2) reads at most 256
tokens and silently drops the rest, so anything longer than that is partly
invisible to search. The target is therefore ~200 tokens (~800 characters),
which leaves headroom for text that tokenizes worse than prose.

Sizing works in two steps. Chunk boundaries are chosen with a character
budget (~4 characters per token, a standard rule of thumb for English prose),
which needs no tokenizer. Callers that have the embedding model's tokenizer
pass it as `token_counter`, and any chunk that still comes out over the token
limit (maths, code and non-English text pack more tokens into each character)
is split again until it fits. Kept as plain functions (not a class) so the
strategy is easy to swap out later.
"""

import re
from dataclasses import dataclass
from typing import Callable, List, Optional, Sequence, Tuple

CHARS_PER_TOKEN = 4
TARGET_TOKENS = 200  # well inside the embedder's 256-token input limit
MAX_CHARS = TARGET_TOKENS * CHARS_PER_TOKEN  # ~800 chars
OVERLAP_RATIO = 0.15  # middle of the requested 10-20% overlap
OVERLAP_CHARS = int(MAX_CHARS * OVERLAP_RATIO)

# Counts the tokens of each text the way the embedding model will.
TokenCounter = Callable[[Sequence[str]], List[int]]

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


def _overlap_tail(text: str, overlap_chars: int) -> str:
    """The last ~`overlap_chars` of `text`, starting on a word boundary.

    A plain slice can begin in the middle of a word ("ord12 word13 ..."); the
    partial word is dropped so the next chunk opens with a whole word. If the
    tail contains no word break at all, there is nothing clean to carry over.
    """
    if not overlap_chars:
        return ""
    tail = text[-overlap_chars:]
    if len(text) <= overlap_chars or text[-overlap_chars - 1].isspace() or tail[0].isspace():
        return tail.strip()
    boundary = re.search(r"\s", tail)
    return tail[boundary.end() :].strip() if boundary else ""


def _split_long_sentence(sentence: str, max_chars: int) -> List[str]:
    """Cut a too-long sentence into pieces of at most `max_chars`, each ending
    at the last whitespace before the limit. Only a run with no whitespace at
    all (a long URL, say) is cut mid-token, because there is nowhere better.
    """
    pieces: List[str] = []
    remaining = sentence.strip()
    while len(remaining) > max_chars:
        window = remaining[: max_chars + 1]  # a break may fall right at the limit
        cut = max(window.rfind(" "), window.rfind("\n"), window.rfind("\t"))
        if cut <= 0:
            cut = max_chars
        piece = remaining[:cut].strip()
        if piece:
            pieces.append(piece)
        remaining = remaining[cut:].strip()
    if remaining:
        pieces.append(remaining)
    return pieces


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
        # A single sentence longer than max_chars has no sentence boundary to
        # respect, so it is split at word boundaries instead.
        if len(sentence) > max_chars:
            if current:
                chunks.append(current.strip())
                current = ""
            chunks.extend(_split_long_sentence(sentence, max_chars))
            continue

        candidate = f"{current} {sentence}".strip() if current else sentence
        if len(candidate) <= max_chars:
            current = candidate
            continue

        chunks.append(current.strip())
        tail = _overlap_tail(current, overlap_chars)
        current = f"{tail} {sentence}".strip() if tail else sentence

    if current.strip():
        chunks.append(current.strip())

    return chunks


# Never shrink below this when re-splitting an over-long chunk; a run of text
# this short that still exceeds the token limit is not real text.
_MIN_RESPLIT_CHARS = 40


def fit_to_token_limit(
    chunks: List[str],
    token_counter: TokenCounter,
    max_tokens: int,
    overlap_ratio: float = OVERLAP_RATIO,
) -> List[str]:
    """Return `chunks` with every chunk of at most `max_tokens` tokens: an
    over-long chunk is split again, with a character budget scaled down by how
    far over it was, until its pieces fit. Order is preserved.
    """
    if not chunks:
        return []
    counts = token_counter(chunks)
    fitted: List[str] = []
    for chunk, tokens in zip(chunks, counts):
        if tokens <= max_tokens:
            fitted.append(chunk)
            continue
        # 0.9: aim a little under the limit so the pieces don't land right on it.
        max_chars = max(_MIN_RESPLIT_CHARS, int(len(chunk) * max_tokens / tokens * 0.9))
        if max_chars >= len(chunk):  # can't shrink further; keep it rather than loop
            fitted.append(chunk)
            continue
        pieces = chunk_text(chunk, max_chars=max_chars, overlap_chars=int(max_chars * overlap_ratio))
        fitted.extend(fit_to_token_limit(pieces, token_counter, max_tokens, overlap_ratio))
    return fitted


def chunk_pages(
    pages: List[Tuple[Optional[int], str]],
    max_chars: int = MAX_CHARS,
    overlap_chars: int = OVERLAP_CHARS,
    token_counter: Optional[TokenCounter] = None,
    max_tokens: Optional[int] = None,
) -> List[ChunkPiece]:
    """Chunk each page independently — a chunk never spans two pages, so
    page attribution stays unambiguous — then number chunks sequentially
    across the whole document.

    With `token_counter` and `max_tokens`, every chunk is also guaranteed to be
    at most `max_tokens` tokens (see fit_to_token_limit).
    """
    pieces: List[ChunkPiece] = []
    index = 0
    for page_number, page_text in pages:
        chunks = chunk_text(page_text, max_chars=max_chars, overlap_chars=overlap_chars)
        if token_counter is not None and max_tokens is not None:
            chunks = fit_to_token_limit(chunks, token_counter, max_tokens)
        for chunk in chunks:
            pieces.append(ChunkPiece(text=chunk, page_number=page_number, chunk_index=index))
            index += 1
    return pieces
