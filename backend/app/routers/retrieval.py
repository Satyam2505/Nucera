from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app import schemas
from app.database import get_db
from app.services.retrieval_service import retrieve_relevant_chunks

router = APIRouter(tags=["retrieval"])


@router.post("/retrieve", response_model=schemas.RetrieveResponse)
def retrieve(payload: schemas.RetrieveRequest, db: Session = Depends(get_db)):
    """Debug/test endpoint for the retrieval pipeline — no LLM involved.
    Lets the retrieval quality be checked directly against uploaded material.
    """
    matches = retrieve_relevant_chunks(
        db,
        payload.question,
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
