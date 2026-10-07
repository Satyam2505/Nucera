import json
import logging
from dataclasses import dataclass
from typing import AsyncIterator, Iterator, List, Optional

import anyio
from fastapi import APIRouter, Depends, Query
from fastapi.responses import Response, StreamingResponse
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import SessionLocal, get_db
from app.deps import get_current_user
from app.ownership import get_owned_topic
from app.services import graph_service, llm_service
from app.services.retrieval_service import retrieve_relevant_chunks
from app.services.tutor_service import (
    PreparedAnswer,
    TutorAnswer,
    answer_prepared,
    is_relevant,
    prepare_tutor_answer,
    stream_tutor_answer,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["tutor"])

# Earlier turns given to the model for follow-up questions.
HISTORY_TURNS = 6
# Most messages one GET /chat returns (the newest ones).
CHAT_PAGE_LIMIT = 200


@dataclass
class _Turn:
    prepared: PreparedAnswer
    flagged_topics: List[models.Topic]


# Chunks fetched when widening to the whole course (some belong to the topic already searched).
COURSE_FALLBACK_CANDIDATES = 8


def _recent_history(db: Session, topic_id: int) -> List[dict]:
    """The topic's last few saved messages, oldest first. Taken from the server,
    not from the request, so a client can't put words in the tutor's mouth."""
    rows = (
        db.query(models.ChatMessage)
        .filter(models.ChatMessage.topic_id == topic_id)
        .order_by(models.ChatMessage.id.desc())
        .limit(HISTORY_TURNS)
        .all()
    )
    return [{"role": row.role, "text": row.content} for row in reversed(rows)]


def _chunk_dict(match: dict, with_topic: bool = False) -> dict:
    chunk = {
        "source": match["source"].title,
        "page": match["chunk"].page_number,
        "text": match["chunk"].chunk_text,
        "similarity": match["similarity_score"],
        "keyword_match": match["keyword_match"],
        "rank": match["rank"],
    }
    if with_topic:
        chunk["topic"] = match["chunk"].topic.name
    return chunk


def _prepare_turn(db: Session, payload: schemas.AskRequest, user: models.User) -> _Turn:
    topic = get_owned_topic(db, payload.topic_id, user)

    # 1. RAG grounding — the best passages from this topic's material.
    matches = retrieve_relevant_chunks(
        db, payload.query, user_id=user.id, topic_id=payload.topic_id, top_k=5
    )
    retrieved_chunks = [_chunk_dict(match) for match in matches]

    # If the topic's own material has nothing relevant, look at the rest of the
    # course before giving up: the answer may be in another topic's notes. Those
    # passages are labelled with their topic, so the answer and its citations say so.
    from_other_topics = False
    if not any(is_relevant(c) for c in retrieved_chunks):
        wider = retrieve_relevant_chunks(
            db,
            payload.query,
            user_id=user.id,
            course_id=topic.module.course_id,
            top_k=COURSE_FALLBACK_CANDIDATES,
        )
        elsewhere = [
            _chunk_dict(match, with_topic=True)
            for match in wider
            if match["chunk"].topic_id != topic.id  # this topic was just searched
        ][:5]
        if any(is_relevant(c) for c in elsewhere):
            retrieved_chunks, from_other_topics = elsewhere, True

    # 2. Adaptive guidance — prerequisite gaps, each paired with its actual
    # mastery score (graph_service only knows which topics are unmastered,
    # not by how much).
    flagged_topics = graph_service.get_unmastered_prerequisites(db, payload.topic_id, user.id)
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

    prepared = prepare_tutor_answer(
        question=payload.query,
        retrieved_chunks=retrieved_chunks,
        topic_name=topic.name,
        topic_mastery_score=topic_score,
        prerequisite_gaps=prerequisite_gaps,
        history=_recent_history(db, payload.topic_id),
        from_other_topics=from_other_topics,
    )
    return _Turn(prepared=prepared, flagged_topics=flagged_topics)


def _save_turn(
    db: Session, topic_id: int, question: str, answer: TutorAnswer, flagged_names: List[str]
) -> None:
    """Store the question and its answer together, so a turn that was abandoned
    part-way leaves no half-conversation behind."""
    db.add(models.ChatMessage(topic_id=topic_id, role="user", content=question))
    db.add(
        models.ChatMessage(
            topic_id=topic_id,
            role="assistant",
            content=answer.answer,
            sources=answer.sources,
            flagged=flagged_names,
            grounded=answer.grounded,
        )
    )
    db.add(
        models.StudySession(topic_id=topic_id, type=models.SessionType.chat, score_delta=0)
    )
    db.commit()


@router.post("/ask", response_model=schemas.AskResponse)
def ask(
    payload: schemas.AskRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    turn = _prepare_turn(db, payload, current_user)
    result = answer_prepared(turn.prepared)
    _save_turn(db, payload.topic_id, payload.query, result, [t.name for t in turn.flagged_topics])

    return schemas.AskResponse(
        answer=result.answer,
        flagged_prerequisites=turn.flagged_topics,
        sources=[schemas.SourceCitation(**s) for s in result.sources],
        grounded=result.grounded,
    )


def _line(event: dict) -> bytes:
    return (json.dumps(event, ensure_ascii=False) + "\n").encode("utf-8")


def _stream_events(
    prepared: PreparedAnswer,
    topic_id: int,
    question: str,
    flagged_names: List[str],
    flagged_json: List[dict],
    abort: Optional[llm_service.StreamAbort] = None,
) -> Iterator[bytes]:
    """The body of /ask/stream. Module-level (and free of the request's session,
    which FastAPI has closed by the time this runs) so it can be driven and
    closed directly. Saving uses its own session. If `abort` is triggered (the
    browser went away) the turn ends quietly: nothing is saved or sent."""
    inner = stream_tutor_answer(prepared, abort)
    answer = None
    try:
        for kind, value in inner:
            if kind == "token":
                yield _line({"type": "token", "text": value})
            else:
                answer = value
        if abort is not None and abort.aborted:
            return
        if answer is None:
            raise RuntimeError("the answer stream ended without a result")
        save_db = SessionLocal()
        try:
            _save_turn(save_db, topic_id, question, answer, flagged_names)
        except Exception:
            save_db.rollback()
            logger.exception("Could not save the chat turn for topic %s", topic_id)
        finally:
            save_db.close()
        yield _line(
            {
                "type": "done",
                "answer": answer.answer,
                "sources": answer.sources,
                "grounded": answer.grounded,
                "flagged_prerequisites": flagged_json,
            }
        )
    except Exception:
        logger.exception("Streaming a tutor answer failed")
        yield _line({"type": "error", "message": "Something went wrong asking the tutor."})
    finally:
        inner.close()  # a browser that went away stops the model too


async def _stream_body(
    prepared: PreparedAnswer,
    topic_id: int,
    question: str,
    flagged_names: List[str],
    flagged_json: List[dict],
) -> AsyncIterator[bytes]:
    """Runs _stream_events in a worker thread, one piece at a time, so the event
    loop stays free. When the browser disconnects, Starlette cancels this; the
    wait on the thread is abandoned (anyio would otherwise defer the cancel until
    the model's next word, which on a CPU can be minutes away) and the model
    connection is closed, which stops the model."""
    abort = llm_service.StreamAbort()
    events = _stream_events(prepared, topic_id, question, flagged_names, flagged_json, abort)
    done = object()
    try:
        while True:
            chunk = await anyio.to_thread.run_sync(next, events, done, abandon_on_cancel=True)
            if chunk is done:
                break
            yield chunk
    finally:
        abort.abort()


@router.post("/ask/stream")
def ask_stream(
    payload: schemas.AskRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """The same answer as /ask, delivered as it is written: one JSON object per
    line, `{"type": "token", "text": ...}` for each piece and then one
    `{"type": "done", ...}` with the final answer, citations, grounded flag and
    prerequisite gaps (an `{"type": "error"}` line instead if something broke).
    Ownership and retrieval are done before the first byte, so a bad topic is an
    ordinary 404, not a stream. Nothing is saved unless the answer completes.
    """
    turn = _prepare_turn(db, payload, current_user)
    flagged_json = [
        schemas.TopicOut.model_validate(t).model_dump(mode="json") for t in turn.flagged_topics
    ]
    return StreamingResponse(
        _stream_body(
            turn.prepared,
            payload.topic_id,
            payload.query,
            [t.name for t in turn.flagged_topics],
            flagged_json,
        ),
        media_type="application/x-ndjson",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/chat/{topic_id}", response_model=List[schemas.ChatMessageOut])
def get_chat(
    topic_id: int,
    limit: int = Query(CHAT_PAGE_LIMIT, ge=1, le=1000),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """The topic's saved conversation, oldest first (the newest `limit` messages)."""
    get_owned_topic(db, topic_id, current_user)
    rows = (
        db.query(models.ChatMessage)
        .filter(models.ChatMessage.topic_id == topic_id)
        .order_by(models.ChatMessage.id.desc())
        .limit(limit)
        .all()
    )
    return list(reversed(rows))


@router.delete("/chat/{topic_id}", status_code=204)
def clear_chat(
    topic_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    get_owned_topic(db, topic_id, current_user)
    db.query(models.ChatMessage).filter(models.ChatMessage.topic_id == topic_id).delete(
        synchronize_session=False
    )
    db.commit()
    return Response(status_code=204)
