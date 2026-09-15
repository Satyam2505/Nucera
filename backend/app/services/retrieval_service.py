"""Semantic retrieval over stored chunks.

Deliberately no vector database: at the scale of one person's course
material (tens to low hundreds of chunks per topic), loading every
candidate chunk's embedding and ranking them with numpy in-process is fast
enough and adds zero new infrastructure. If chunk counts ever grow large
enough for this to matter, this is the one function to swap out — nothing
else needs to change, since callers only ever see retrieve_relevant_chunks().
"""

from typing import List, Optional

import numpy as np
from sqlalchemy.orm import Session

from app import models
from app.services.embedding_service import EMBEDDING_DIM, generate_embedding


def retrieve_relevant_chunks(
    db: Session,
    question: str,
    topic_id: Optional[int] = None,
    source_ids: Optional[List[int]] = None,
    top_k: int = 5,
) -> List[dict]:
    """Embed `question`, rank stored chunks by cosine similarity to it, and
    return the top_k matches with their source metadata.

    Each result is a plain dict (not an ORM object) so it can be handed
    straight to a Pydantic response model or used as tutor context:
    {chunk, source, similarity_score}
    """
    query = (
        db.query(models.Chunk)
        .join(models.Source, models.Chunk.source_id == models.Source.id)
    )
    if topic_id is not None:
        query = query.filter(models.Chunk.topic_id == topic_id)
    if source_ids:
        query = query.filter(models.Chunk.source_id.in_(source_ids))

    candidates = [c for c in query.all() if c.embedding and len(c.embedding) == EMBEDDING_DIM]
    if not candidates:
        return []

    question_vec = np.asarray(generate_embedding(question), dtype=np.float32)
    chunk_matrix = np.asarray([c.embedding for c in candidates], dtype=np.float32)

    # generate_embedding() already L2-normalizes, but the question vector and
    # any chunk row are normalized again here defensively — cheap, and keeps
    # this function correct even if that assumption ever changes upstream.
    question_norm = question_vec / (np.linalg.norm(question_vec) or 1.0)
    chunk_norms = np.linalg.norm(chunk_matrix, axis=1, keepdims=True)
    chunk_norms[chunk_norms == 0] = 1.0
    normalized_chunks = chunk_matrix / chunk_norms

    similarities = normalized_chunks @ question_norm

    order = np.argsort(-similarities)[:top_k]

    results = []
    for i in order:
        chunk = candidates[i]
        results.append(
            {
                "chunk": chunk,
                "source": chunk.source,
                "similarity_score": float(similarities[i]),
            }
        )
    return results
