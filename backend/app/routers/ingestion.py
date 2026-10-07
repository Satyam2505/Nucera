import logging
from typing import List, Optional, Tuple

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app import models, schemas
from app.config import UPLOAD_MAX_BYTES
from app.database import get_db
from app.deps import get_current_user
from app.ownership import get_owned_source, get_owned_topic
from app.services.embedding_service import embed_texts
from app.services.indexing import chunk_for_embedding
from app.services.text_extraction import UploadRejected, check_extension, extract_pages

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/sources", tags=["ingestion"])

EMBEDDING_FAILED_MESSAGE = (
    "Couldn't process this material right now (the embedding step failed). Nothing was saved."
)
# Matches Source.title / Source.file_path.
MAX_TITLE_CHARS = 255


def _too_large(what: str) -> UploadRejected:
    return UploadRejected(
        413, f"{what} is too large (the limit is {UPLOAD_MAX_BYTES / (1024 * 1024):g} MB)."
    )


def _ingest_pages(
    db: Session,
    topic: models.Topic,
    source_type: models.SourceType,
    title: str,
    pages: List[Tuple[Optional[int], str]],
    file_path: Optional[str] = None,
) -> models.Source:
    """Chunk and embed first, then write the source and all its chunks in one
    transaction, so a failure part-way never leaves a source without chunks."""
    try:
        pieces = chunk_for_embedding(pages)
        embeddings = embed_texts([piece.text for piece in pieces]) if pieces else []
    except Exception:
        logger.exception("Embedding failed while ingesting %r", title)
        raise HTTPException(status_code=503, detail=EMBEDDING_FAILED_MESSAGE)
    if not pieces:
        raise HTTPException(status_code=422, detail="There is no text to add.")
    if len(embeddings) != len(pieces):
        raise HTTPException(status_code=503, detail=EMBEDDING_FAILED_MESSAGE)

    source = models.Source(
        topic_id=topic.id,
        source_type=source_type,
        title=title,
        raw_text="\n\n".join(text for _, text in pages),
        file_path=file_path,
    )
    for piece, embedding in zip(pieces, embeddings):
        source.chunks.append(
            models.Chunk(
                topic_id=topic.id,
                chunk_text=piece.text,
                chunk_index=piece.chunk_index,
                page_number=piece.page_number,
                embedding=embedding,
            )
        )
    db.add(source)
    try:
        db.commit()
    except Exception:
        db.rollback()
        raise
    db.refresh(source)
    return source


@router.post("/text", response_model=schemas.SourceOut)
def ingest_text(
    payload: schemas.IngestTextRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    topic = get_owned_topic(db, payload.topic_id, current_user)
    # The same cap as an uploaded file, so pasting can't be used to get around it
    # (characters, not bytes: close enough for a size guard).
    if len(payload.text) > UPLOAD_MAX_BYTES:
        exc = _too_large("Text")
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)
    return _ingest_pages(db, topic, payload.source_type, payload.title, [(None, payload.text)])


# A plain `def`, not `async def`: extracting a PDF and embedding the chunks are
# CPU-bound and take seconds, and FastAPI runs a sync route in its worker
# threadpool, so they can't freeze the event loop (and every other request)
# while an upload is processed. The body has already been spooled by
# Starlette, so the read below is an ordinary blocking read of a local file,
# and the DB session stays on this one thread.
@router.post("/upload", response_model=schemas.SourceOut)
def ingest_file(
    topic_id: int = Form(...),
    source_type: models.SourceType = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    # Ownership first, so nothing of someone else's topic is read or processed.
    topic = get_owned_topic(db, topic_id, current_user)

    filename = (file.filename or "uploaded file")[:MAX_TITLE_CHARS]
    try:
        check_extension(filename)  # refuse the type before reading the body
        # Starlette has already spooled the upload to a temporary file, so the
        # limit here is about memory: never read more than limit + 1 bytes,
        # which is enough to tell that the file is too big.
        raw_bytes = file.file.read(UPLOAD_MAX_BYTES + 1)
        if len(raw_bytes) > UPLOAD_MAX_BYTES:
            raise _too_large("File")
        pages = extract_pages(filename, raw_bytes)
    except UploadRejected as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.detail)

    return _ingest_pages(db, topic, source_type, filename, pages, file_path=filename)


@router.get("/topic/{topic_id}", response_model=list[schemas.SourceOut])
def list_sources_for_topic(
    topic_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    get_owned_topic(db, topic_id, current_user)
    return db.query(models.Source).filter(models.Source.topic_id == topic_id).all()


@router.delete("/{source_id}", status_code=204)
def delete_source(
    source_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    source = get_owned_source(db, source_id, current_user)
    db.delete(source)
    db.commit()
