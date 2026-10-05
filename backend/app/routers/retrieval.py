from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.deps import get_current_user
from app.ownership import get_owned_topic
from app.services.retrieval_service import retrieve_relevant_chunks

router = APIRouter(tags=["retrieval"])


@router.post("/retrieve", response_model=schemas.RetrieveResponse)
def retrieve(
    payload: schemas.RetrieveRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Debug/test endpoint for the retrieval pipeline — no LLM involved.
    Lets the retrieval quality be checked directly against uploaded material.
    """
    if payload.topic_id is not None:
        get_owned_topic(db, payload.topic_id, current_user)

    # Only the caller's own chunks are ever searched, with or without a topic.
    matches = retrieve_relevant_chunks(
        db,
        payload.question,
        user_id=current_user.id,
        topic_id=payload.topic_id,
        source_ids=payload.source_ids,
        top_k=payload.top_k,
    )

    results = [
        schemas.RetrievedChunk(
            chunk_id=match["chunk"].id,
            source_id=match["source"].id,
            filename=match["source"].title,
            page_number=match["chunk"].page_number,
            chunk_index=match["chunk"].chunk_index,
            similarity_score=match["similarity_score"],
            chunk_text=match["chunk"].chunk_text,
        )
        for match in matches
    ]

    return schemas.RetrieveResponse(question=payload.question, results=results)
