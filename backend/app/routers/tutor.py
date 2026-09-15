from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.services import graph_service
from app.services.retrieval_service import retrieve_relevant_chunks
from app.services.tutor_service import generate_tutor_answer

router = APIRouter(tags=["tutor"])


@router.post("/ask", response_model=schemas.AskResponse)
def ask(payload: schemas.AskRequest, db: Session = Depends(get_db)):
    topic = db.get(models.Topic, payload.topic_id)
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")

    # 1. RAG grounding — the top relevant chunks from this topic's material.
    matches = retrieve_relevant_chunks(db, payload.query, topic_id=payload.topic_id, top_k=5)
    retrieved_chunks = [
        {
            "source": match["source"].title,
            "page": match["chunk"].page_number,
            "text": match["chunk"].chunk_text,
            "similarity": match["similarity_score"],
        }
        for match in matches
    ]

    # 2. Adaptive guidance — prerequisite gaps, each paired with its actual
    # mastery score (graph_service only knows which topics are unmastered,
    # not by how much).
    flagged_topics = graph_service.get_unmastered_prerequisites(db, payload.topic_id)
    gap_mastery_by_topic = {
        m.topic_id: m
        for m in db.query(models.Mastery)
        .filter(models.Mastery.topic_id.in_([t.id for t in flagged_topics]))
        .all()
    }
    prerequisite_gaps = [
        {"name": t.name, "score": gap_mastery_by_topic[t.id].score if t.id in gap_mastery_by_topic else 0}
        for t in flagged_topics
    ]

    topic_mastery = db.get(models.Mastery, payload.topic_id)
    topic_score = topic_mastery.score if topic_mastery else 0

    history = [turn.model_dump() for turn in (payload.history or [])]

    result = generate_tutor_answer(
        question=payload.query,
        retrieved_chunks=retrieved_chunks,
        topic_name=topic.name,
        topic_mastery_score=topic_score,
        prerequisite_gaps=prerequisite_gaps,
        history=history,
    )

    db.add(
        models.StudySession(
            topic_id=payload.topic_id, type=models.SessionType.chat, score_delta=0
        )
    )
    db.commit()

    return schemas.AskResponse(
        answer=result.answer,
        flagged_prerequisites=flagged_topics,
        sources=[schemas.SourceCitation(**s) for s in result.sources],
        grounded=result.grounded,
    )
