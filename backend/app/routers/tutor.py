from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.services import graph_service
from app.services.retrieval_service import retrieve_relevant_chunks
from app.services.tutor_service import generate_tutor_response

router = APIRouter(tags=["tutor"])


@router.post("/ask", response_model=schemas.AskResponse)
def ask(payload: schemas.AskRequest, db: Session = Depends(get_db)):
    topic = db.get(models.Topic, payload.topic_id)
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")

    # Real retrieval: rank this topic's chunks by relevance to the question
    # instead of grabbing whichever ones happened to be inserted first.
    matches = retrieve_relevant_chunks(db, payload.query, topic_id=payload.topic_id, top_k=5)
    context_chunks = [match["chunk"].chunk_text for match in matches]

    flagged = graph_service.get_unmastered_prerequisites(db, payload.topic_id)

    # generate_tutor_response is still the STUB — it now receives real
    # retrieved context and real prerequisite gaps, but the answer itself
    # (and the flagged list surfaced to the user) isn't generated from them
    # yet. That's the next milestone, not this one.
    answer = generate_tutor_response(payload.query, context_chunks, topic.name)

    db.add(
        models.StudySession(
            topic_id=payload.topic_id, type=models.SessionType.chat, score_delta=0
        )
    )
    db.commit()

    return schemas.AskResponse(answer=answer, flagged_prerequisites=flagged)
