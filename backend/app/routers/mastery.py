from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db

router = APIRouter(tags=["mastery"])


def apply_score_delta(mastery: models.Mastery, score_delta: int) -> None:
    mastery.score = max(0, min(100, mastery.score + score_delta))
    if mastery.score >= 80:
        mastery.status = models.MasteryStatus.mastered
    elif mastery.score > 0:
        mastery.status = models.MasteryStatus.in_progress


@router.get("/mastery", response_model=list[schemas.MasteryOut])
def list_mastery(db: Session = Depends(get_db)):
    return db.query(models.Mastery).all()


@router.get("/mastery/{topic_id}", response_model=schemas.MasteryOut)
def get_mastery(topic_id: int, db: Session = Depends(get_db)):
    mastery = db.get(models.Mastery, topic_id)
    if not mastery:
        raise HTTPException(status_code=404, detail="Mastery record not found")
    return mastery


@router.put("/mastery/{topic_id}", response_model=schemas.MasteryOut)
def update_mastery(
    topic_id: int, payload: schemas.MasteryUpdate, db: Session = Depends(get_db)
):
    mastery = db.get(models.Mastery, topic_id)
    if not mastery:
        raise HTTPException(status_code=404, detail="Mastery record not found")

    if payload.score is not None:
        mastery.score = max(0, min(100, payload.score))
    if payload.status is not None:
        mastery.status = payload.status

    db.commit()
    db.refresh(mastery)
    return mastery


@router.post("/mastery/{topic_id}/missed", response_model=schemas.MasteryOut)
def mark_missed(topic_id: int, db: Session = Depends(get_db)):
    mastery = db.get(models.Mastery, topic_id)
    if not mastery:
        raise HTTPException(status_code=404, detail="Mastery record not found")

    mastery.status = models.MasteryStatus.missed
    db.commit()
    db.refresh(mastery)
    return mastery


@router.post("/sessions", response_model=schemas.SessionOut)
def record_session(payload: schemas.SessionCreate, db: Session = Depends(get_db)):
    mastery = db.get(models.Mastery, payload.topic_id)
    if not mastery:
        raise HTTPException(status_code=404, detail="Mastery record not found")

    session = models.StudySession(**payload.model_dump())
    db.add(session)

    apply_score_delta(mastery, payload.score_delta)

    db.commit()
    db.refresh(session)
    return session
