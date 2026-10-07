"""Rebuilding stored chunks and embeddings from the text already in the database.

Needed when the chunking or the embedding model changes, so chunks written
earlier no longer fit (see chunking.py). There is no re-extraction: the
original upload isn't kept, only `sources.raw_text` and the chunks.

Page numbers are the catch. `raw_text` is every page joined together, so on its
own it can't say where one page ends. They are recovered from the old chunks
instead: the chunker never lets a chunk span two pages, and it copies the tail
of each chunk to the start of the next (the overlap). So the old chunks of one
page, with that overlap removed again, are exactly that page's text. Each
reconstruction is then checked against `raw_text` (same words, same order); if
the check fails the source is left alone rather than re-indexed with guessed or
lost page numbers.

Each source is replaced in one transaction, after its new chunks have been
embedded, so a failure leaves that source exactly as it was.
"""

import logging
import re
from dataclasses import dataclass
from typing import Callable, List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from app import models
from app.services.chunking import MAX_CHARS, OVERLAP_CHARS
from app.services.embedding_service import count_tokens, embed_texts, max_input_tokens
from app.services.indexing import chunk_for_embedding

logger = logging.getLogger(__name__)

Pages = List[Tuple[Optional[int], str]]

# A seam overlap shorter than this is treated as coincidence, not as the copied tail.
_MIN_OVERLAP_CHARS = 12

# A chunk longer than this can't have been written by the current chunker (its
# character budget plus one overlap), so it is from an older, larger setting.
STALE_CHUNK_CHARS = MAX_CHARS + OVERLAP_CHARS + 20


@dataclass
class SourceResult:
    source_id: int
    title: str
    # "reindexed", "up_to_date", "skipped" (left untouched; see `reason`), "failed"
    status: str
    old_chunks: int = 0
    new_chunks: int = 0
    reason: str = ""
    # False only when a source that had page numbers was re-indexed without them.
    pages_preserved: bool = True


def _normalize(text: str) -> str:
    return " ".join(text.split())


def _stitch(texts: List[str]) -> str:
    """Join the consecutive chunks of one page back into the page's text,
    dropping the overlap the chunker copied from each chunk to the next."""
    if not texts:
        return ""
    result = texts[0]
    for following in texts[1:]:
        overlap = 0
        for size in range(min(len(result), len(following)), _MIN_OVERLAP_CHARS - 1, -1):
            if result.endswith(following[:size]):
                overlap = size
                break
        rest = following[overlap:].strip()
        result = f"{result} {rest}" if rest else result
    return result


def reconstruct_pages(chunks: List[models.Chunk]) -> Pages:
    """The (page number, text) pairs the old chunks were made from, in order."""
    pages: Pages = []
    group: List[str] = []
    current: Optional[int] = None
    started = False
    for chunk in sorted(chunks, key=lambda c: c.chunk_index):
        if started and chunk.page_number != current:
            pages.append((current, _stitch(group)))
            group = []
        current = chunk.page_number
        started = True
        group.append(chunk.chunk_text)
    if started:
        pages.append((current, _stitch(group)))
    return pages


def pages_for_source(source: models.Source) -> Tuple[Optional[Pages], str]:
    """(pages to re-chunk, reason if there are none).

    `pages` is None when the source can't be rebuilt without losing or guessing
    page numbers.
    """
    chunks = list(source.chunks)
    raw = source.raw_text or ""
    if not chunks and not raw.strip():
        return None, "no text stored"
    paged = any(c.page_number is not None for c in chunks)

    if not paged:
        # Plain text has no pages, so raw_text is the whole story.
        if raw.strip():
            return [(None, raw)], ""
        return None, "no raw_text and no page numbers to rebuild from"

    rebuilt = reconstruct_pages(chunks)
    if not raw.strip():
        return None, "has page numbers but no raw_text to verify them against"
    if _normalize(" ".join(text for _, text in rebuilt)) != _normalize(raw):
        return None, "page text could not be rebuilt from its chunks and checked against raw_text"
    return rebuilt, ""


def _fits(chunks: List[models.Chunk]) -> bool:
    if not chunks:
        return True
    limit = max_input_tokens()
    return all(tokens <= limit for tokens in count_tokens([c.chunk_text for c in chunks]))


def reindex_source(
    db: Session,
    source: models.Source,
    *,
    force: bool = False,
    allow_page_loss: bool = False,
    dry_run: bool = False,
) -> SourceResult:
    old = list(source.chunks)
    result = SourceResult(source_id=source.id, title=source.title, status="up_to_date", old_chunks=len(old))

    if not force and _fits(old):
        return result

    pages, reason = pages_for_source(source)
    if pages is None:
        if not allow_page_loss or not (source.raw_text or "").strip():
            result.status = "skipped"
            result.reason = reason
            return result
        pages = [(None, source.raw_text)]
        result.pages_preserved = False

    pieces = chunk_for_embedding(pages)
    result.new_chunks = len(pieces)
    if not pieces:
        result.status = "skipped"
        result.reason = "re-chunking produced no text"
        return result
    if dry_run:
        result.status = "reindexed"
        return result

    embeddings = embed_texts([piece.text for piece in pieces])
    if len(embeddings) != len(pieces):
        result.status = "failed"
        result.reason = "the embedding step returned the wrong number of vectors"
        return result

    try:
        db.query(models.Chunk).filter(models.Chunk.source_id == source.id).delete(
            synchronize_session=False
        )
        for piece, embedding in zip(pieces, embeddings):
            db.add(
                models.Chunk(
                    source_id=source.id,
                    topic_id=source.topic_id,
                    chunk_text=piece.text,
                    chunk_index=piece.chunk_index,
                    page_number=piece.page_number,
                    embedding=embedding,
                )
            )
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Re-indexing source %s failed; it was left unchanged", source.id)
        result.status = "failed"
        result.reason = "writing the new chunks failed; the source is unchanged"
        return result

    db.expire(source, ["chunks"])
    result.status = "reindexed"
    return result


def reindex_all(
    db: Session,
    *,
    force: bool = False,
    allow_page_loss: bool = False,
    dry_run: bool = False,
    on_result: Optional[Callable[[SourceResult], None]] = None,
) -> List[SourceResult]:
    results: List[SourceResult] = []
    for source_id in [row[0] for row in db.query(models.Source.id).order_by(models.Source.id)]:
        source = db.get(models.Source, source_id)
        try:
            outcome = reindex_source(
                db, source, force=force, allow_page_loss=allow_page_loss, dry_run=dry_run
            )
        except Exception as exc:  # one bad source must not stop the rest
            db.rollback()
            logger.exception("Re-indexing source %s failed", source_id)
            outcome = SourceResult(
                source_id=source_id,
                title=source.title if source else "?",
                status="failed",
                reason=str(exc) or exc.__class__.__name__,
            )
        results.append(outcome)
        if on_result:
            on_result(outcome)
    return results


def count_stale(db: Session) -> Tuple[int, int]:
    """(chunks, sources) holding a chunk too long for the current chunker to have
    written. A cheap length check, no model needed, for a startup warning; it
    misses an old chunk that happens to be short, which doesn't matter because
    a short chunk fits the embedder anyway."""
    over = models.Chunk.chunk_text
    chunk_count, source_count = db.query(
        func.count(models.Chunk.id), func.count(func.distinct(models.Chunk.source_id))
    ).filter(func.length(over) > STALE_CHUNK_CHARS).one()
    return int(chunk_count), int(source_count)
