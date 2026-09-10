from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.services.chunking import chunk_text
from app.services.embedding_service import generate_embedding

router = APIRouter(prefix="/sources", tags=["ingestion"])


def _ingest(
    db: Session,
    topic_id: int,
    source_type: models.SourceType,
    title: str,
    text: str,
    file_path: Optional[str] = None,
) -> models.Source:
    topic = db.get(models.Topic, topic_id)
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")

    source = models.Source(
        topic_id=topic_id,
        source_type=source_type,
        title=title,
        raw_text=text,
        file_path=file_path,
    )
    db.add(source)
    db.commit()
    db.refresh(source)

    for index, chunk in enumerate(chunk_text(text)):
        db.add(
            models.Chunk(
                source_id=source.id,
                topic_id=topic_id,
                chunk_text=chunk,
                chunk_index=index,
                embedding=generate_embedding(chunk),
            )
        )
    db.commit()

    return source


@router.post("/text", response_model=schemas.SourceOut)
def ingest_text(payload: schemas.IngestTextRequest, db: Session = Depends(get_db)):
    return _ingest(db, payload.topic_id, payload.source_type, payload.title, payload.text)


@router.post("/upload", response_model=schemas.SourceOut)
async def ingest_file(
    topic_id: int = Form(...),
    source_type: models.SourceType = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    # Naive plain-text decode — real PDF/PPT parsing is out of scope for this
    # scaffold and will be added alongside the real ingestion pipeline.
    raw_bytes = await file.read()
    text = raw_bytes.decode("utf-8", errors="ignore")

    return _ingest(
        db, topic_id, source_type, file.filename or "uploaded file", text, file_path=file.filename
    )


@router.get("/topic/{topic_id}", response_model=list[schemas.SourceOut])
def list_sources_for_topic(topic_id: int, db: Session = Depends(get_db)):
    return db.query(models.Source).filter(models.Source.topic_id == topic_id).all()
