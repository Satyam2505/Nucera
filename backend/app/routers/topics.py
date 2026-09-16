from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.deps import get_current_user
from app.services import graph_service

router = APIRouter(prefix="/topics", tags=["topics"])


@router.get("", response_model=list[schemas.TopicOut])
def list_topics(
    db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)
):
    return db.query(models.Topic).filter(models.Topic.user_id == current_user.id).all()


@router.post("", response_model=schemas.TopicOut)
def create_topic(
    payload: schemas.TopicCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    topic = models.Topic(**payload.model_dump(), user_id=current_user.id)
    db.add(topic)
    db.commit()
    db.refresh(topic)

    db.add(models.Mastery(topic_id=topic.id))
    db.commit()

    return topic


@router.post("/prerequisites")
def add_prerequisite(
    payload: schemas.PrerequisiteCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    if payload.topic_id == payload.prerequisite_topic_id:
        raise HTTPException(status_code=400, detail="A topic cannot be its own prerequisite")

    for topic_id in (payload.topic_id, payload.prerequisite_topic_id):
        topic = db.get(models.Topic, topic_id)
        if not topic or topic.user_id != current_user.id:
            raise HTTPException(status_code=404, detail="Topic not found")

    existing = db.get(
        models.Prerequisite, (payload.topic_id, payload.prerequisite_topic_id)
    )
    if existing:
        raise HTTPException(status_code=400, detail="Prerequisite already exists")

    db.add(models.Prerequisite(**payload.model_dump()))
    db.commit()
    return {"status": "ok"}


@router.get("/graph/json")
def get_graph(
    db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)
):
    return graph_service.get_graph_json(db, user_id=current_user.id)


@router.get("/graph/order", response_model=list[schemas.TopicOut])
def get_order(
    db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)
):
    return graph_service.get_topic_order(db, user_id=current_user.id)


@router.get("/{topic_id}", response_model=schemas.TopicOut)
def get_topic(
    topic_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    topic = db.get(models.Topic, topic_id)
    if not topic or topic.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Topic not found")
    return topic
