"""Hybrid retrieval over stored chunks: vectors for meaning, keywords for exact terms.

Deliberately no vector database: at the scale of one person's course
material (tens to low hundreds of chunks per topic), loading every
candidate chunk's embedding and ranking them with numpy in-process is fast
enough and adds zero new infrastructure. If chunk counts ever grow large
enough for this to matter, this is the one function to swap out — nothing
else needs to change, since callers only ever see retrieve_relevant_chunks().

The vector ranking misses exact terms (an acronym, a formula, a rare word), so
when SQLite's FTS5 index is available (services/fts.py) a keyword ranking is
computed too and the two are merged with reciprocal rank fusion: each chunk scores
1/(k + rank) in every ranking it appears in, and the scores are added. RRF needs no
tuning of score scales, which differ completely between cosine similarity and BM25.
"""

from typing import Dict, List, Optional

import numpy as np
from sqlalchemy.orm import Session

from app import models
from app.config import HYBRID_LEXICAL_LIMIT, HYBRID_RRF_K, RETRIEVAL_HYBRID
from app.services import fts
from app.services.embedding_service import EMBEDDING_DIM, generate_embedding


def reciprocal_rank_fusion(rankings: List[List[int]], k: int = HYBRID_RRF_K) -> Dict[int, float]:
    """Merge best-first rankings of ids: score(id) = sum over rankings of 1 / (k + rank),
    with rank starting at 1. An id missing from a ranking gets nothing from it."""
    scores: Dict[int, float] = {}
    for ranking in rankings:
        for position, item in enumerate(ranking, start=1):
            scores[item] = scores.get(item, 0.0) + 1.0 / (k + position)
    return scores


def retrieve_relevant_chunks(
    db: Session,
    question: str,
    user_id: int,
    topic_id: Optional[int] = None,
    source_ids: Optional[List[int]] = None,
    top_k: int = 5,
    course_id: Optional[int] = None,
    hybrid: Optional[bool] = None,
) -> List[dict]:
    """Rank stored chunks against `question` and return the top_k with their source
    metadata, best first.

    Only chunks in `user_id`'s own courses are ever searched; user_id is
    required so a caller can't search across accounts by leaving it out. The scope
    can be narrowed to a topic, to a course (all its topics), or to given sources.

    Each result is a plain dict (not an ORM object) so it can be handed
    straight to a Pydantic response model or used as tutor context:
    {chunk, source, similarity_score, keyword_match, rank}

    `similarity_score` is always the cosine similarity of the chunk to the question
    (what the relevance threshold is measured on). `keyword_match` is True when the
    chunk contains EVERY searchable word of the question: a precise signal, which
    the tutor accepts as relevance even when the cosine similarity is low. `rank` is
    the position after merging the two rankings (1 = best).
    """
    query = (
        db.query(models.Chunk)
        .join(models.Source, models.Chunk.source_id == models.Source.id)
        .join(models.Topic, models.Chunk.topic_id == models.Topic.id)
        .join(models.Module, models.Topic.module_id == models.Module.id)
        .join(models.Course, models.Module.course_id == models.Course.id)
        .filter(models.Course.user_id == user_id)
    )
    if topic_id is not None:
        query = query.filter(models.Chunk.topic_id == topic_id)
    if course_id is not None:
        query = query.filter(models.Course.id == course_id)
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
    vector_order = [int(i) for i in np.argsort(-similarities)]
    ids = [c.id for c in candidates]

    rankings = [[ids[i] for i in vector_order]]
    strict_ids: set = set()
    use_hybrid = RETRIEVAL_HYBRID if hybrid is None else hybrid
    if use_hybrid and fts.fts_available(db):
        strict, loose = fts.match_expressions(fts.query_terms(question))
        if loose is not None:
            scope = dict(
                user_id=user_id, topic_id=topic_id, course_id=course_id, source_ids=source_ids
            )
            keyword_ranking = fts.search(db, loose, limit=HYBRID_LEXICAL_LIMIT, **scope)
            keyword_ranking = [cid for cid in keyword_ranking if cid in set(ids)]
            if keyword_ranking:
                rankings.append(keyword_ranking)
                strict_ids = set(
                    fts.search(db, strict, limit=len(ids) or HYBRID_LEXICAL_LIMIT, **scope)
                )

    fused = reciprocal_rank_fusion(rankings)
    index_by_id = {cid: i for i, cid in enumerate(ids)}
    # Ties (chunks with the same fused score) keep the vector order.
    vector_position = {cid: p for p, cid in enumerate(rankings[0])}
    order = sorted(fused, key=lambda cid: (-fused[cid], vector_position[cid]))[:top_k]

    results = []
    for rank, cid in enumerate(order, start=1):
        i = index_by_id[cid]
        chunk = candidates[i]
        results.append(
            {
                "chunk": chunk,
                "source": chunk.source,
                "similarity_score": float(similarities[i]),
                "keyword_match": cid in strict_ids,
                "rank": rank,
            }
        )
    return results
