from typing import List, Optional, Tuple

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.services.chunking import chunk_pages
from app.services.embedding_service import embed_texts
from app.services.text_extraction import extract_pages

router = APIRouter(prefix="/sources", tags=["ingestion"])


def _ingest_pages(
    db: Session,
    topic_id: int,
    source_type: models.SourceType,
    title: str,
    pages: List[Tuple[Optional[int], str]],
    file_path: Optional[str] = None,
) -> models.Source:
    topic = db.get(models.Topic, topic_id)
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")

    source = models.Source(
        topic_id=topic_id,
        source_type=source_type,
        title=title,
        raw_text="\n\n".join(text for _, text in pages),
        file_path=file_path,
    )
    db.add(source)
    db.commit()
    db.refresh(source)

    pieces = chunk_pages(pages)
    if pieces:
        embeddings = embed_texts([piece.text for piece in pieces])
        for piece, embedding in zip(pieces, embeddings):
            db.add(
                models.Chunk(
                    source_id=source.id,
                    topic_id=topic_id,
                    chunk_text=piece.text,
                    chunk_index=piece.chunk_index,
                    page_number=piece.page_number,
                    embedding=embedding,
                )
            )
        db.commit()

    return source


@router.post("/text", response_model=schemas.SourceOut)
def ingest_text(payload: schemas.IngestTextRequest, db: Session = Depends(get_db)):
    return _ingest_pages(
        db, payload.topic_id, payload.source_type, payload.title, [(None, payload.text)]
    )


@router.post("/upload", response_model=schemas.SourceOut)
async def ingest_file(
    topic_id: int = Form(...),
    source_type: models.SourceType = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    raw_bytes = await file.read()
    filename = file.filename or "uploaded file"

    pages = extract_pages(filename, raw_bytes)
    if not pages:
        raise HTTPException(
            status_code=400, detail="Could not extract any text from the uploaded file"
        )

    return _ingest_pages(
        db, topic_id, source_type, filename, pages, file_path=filename
    )


@router.get("/topic/{topic_id}", response_model=list[schemas.SourceOut])
def list_sources_for_topic(topic_id: int, db: Session = Depends(get_db)):
    return db.query(models.Source).filter(models.Source.topic_id == topic_id).all()
