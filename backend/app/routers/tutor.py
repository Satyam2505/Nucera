from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.services import graph_service
from app.services.tutor_service import generate_tutor_response

router = APIRouter(tags=["tutor"])


@router.post("/ask", response_model=schemas.AskResponse)
def ask(payload: schemas.AskRequest, db: Session = Depends(get_db)):
    topic = db.get(models.Topic, payload.topic_id)
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")

    chunks = (
        db.query(models.Chunk)
        .filter(models.Chunk.topic_id == payload.topic_id)
        .limit(5)
        .all()
    )
    context_chunks = [c.chunk_text for c in chunks]

    answer = generate_tutor_response(payload.query, context_chunks, topic.name)
    flagged = graph_service.get_unmastered_prerequisites(db, payload.topic_id)

    db.add(
        models.StudySession(
            topic_id=payload.topic_id, type=models.SessionType.chat, score_delta=0
        )
    )
    db.commit()

    return schemas.AskResponse(answer=answer, flagged_prerequisites=flagged)
