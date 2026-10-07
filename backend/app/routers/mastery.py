from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.deps import get_current_user
from app.ownership import get_owned_course, get_owned_topic
from app.services.mastery_service import apply_score_delta, set_score

router = APIRouter(tags=["mastery"])


def _owned_mastery(db: Session, topic_id: int, user: models.User) -> models.Mastery:
    """The mastery row of one of the caller's own topics (404 otherwise)."""
    get_owned_topic(db, topic_id, user)
    mastery = db.get(models.Mastery, topic_id)
    if not mastery:
        raise HTTPException(status_code=404, detail="Mastery record not found")
    return mastery


@router.get("/mastery", response_model=list[schemas.MasteryOut])
def list_mastery(
    db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)
):
    return (
        db.query(models.Mastery)
        .join(models.Topic, models.Mastery.topic_id == models.Topic.id)
        .join(models.Module, models.Topic.module_id == models.Module.id)
        .join(models.Course, models.Module.course_id == models.Course.id)
        .filter(models.Course.user_id == current_user.id)
        .order_by(models.Mastery.topic_id)
        .all()
    )


@router.get("/mastery/{topic_id}", response_model=schemas.MasteryOut)
def get_mastery(
    topic_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    return _owned_mastery(db, topic_id, current_user)


@router.put("/mastery/{topic_id}", response_model=schemas.MasteryOut)
def update_mastery(
    topic_id: int,
    payload: schemas.MasteryUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    mastery = _owned_mastery(db, topic_id, current_user)

    # The status follows from the score (see mastery_service); it can't be
    # set directly here, only via POST .../missed.
    if payload.score is not None:
        set_score(mastery, payload.score)

    db.commit()
    db.refresh(mastery)
    return mastery


@router.post("/mastery/{topic_id}/toggle-revision", response_model=schemas.MasteryOut)
def toggle_revision(
    topic_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    mastery = _owned_mastery(db, topic_id, current_user)

    mastery.flagged_for_revision = not mastery.flagged_for_revision
    db.commit()
    db.refresh(mastery)
    return mastery


@router.post("/mastery/{topic_id}/missed", response_model=schemas.MasteryOut)
def mark_missed(
    topic_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    mastery = _owned_mastery(db, topic_id, current_user)

    mastery.status = models.MasteryStatus.missed
    db.commit()
    db.refresh(mastery)
    return mastery


@router.post("/sessions", response_model=schemas.SessionOut)
def record_session(
    payload: schemas.SessionCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    mastery = _owned_mastery(db, payload.topic_id, current_user)

    session = models.StudySession(**payload.model_dump())
    db.add(session)

    apply_score_delta(mastery, payload.score_delta)

    db.commit()
    db.refresh(session)
    return session


@router.get("/sessions", response_model=List[schemas.SessionHistoryItem])
def list_sessions(
    topic_id: Optional[int] = None,
    course_id: Optional[int] = None,
    before_id: Optional[int] = Query(default=None, ge=1),
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """The caller's study-session history, newest first: chats, graded quizzes and
    self reports. Narrow it to one topic or one course (each checked for
    ownership); with neither, it covers all of the caller's courses. Page back
    with `before_id` set to the last id received."""
    if topic_id is not None:
        get_owned_topic(db, topic_id, current_user)
    if course_id is not None:
        get_owned_course(db, course_id, current_user)

    query = (
        db.query(models.StudySession, models.Topic.name)
        .join(models.Topic, models.StudySession.topic_id == models.Topic.id)
        .join(models.Module, models.Topic.module_id == models.Module.id)
        .join(models.Course, models.Module.course_id == models.Course.id)
        .filter(models.Course.user_id == current_user.id)
    )
    if topic_id is not None:
        query = query.filter(models.StudySession.topic_id == topic_id)
    if course_id is not None:
        query = query.filter(models.Course.id == course_id)
    if before_id is not None:
        query = query.filter(models.StudySession.id < before_id)
    rows = query.order_by(models.StudySession.id.desc()).limit(limit).all()
    return [
        schemas.SessionHistoryItem(
            id=session.id,
            topic_id=session.topic_id,
            topic_name=name,
            type=session.type,
            score_delta=session.score_delta,
            timestamp=session.timestamp,
        )
        for session, name in rows
    ]
