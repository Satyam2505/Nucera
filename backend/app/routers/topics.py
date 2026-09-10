from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.services import graph_service

router = APIRouter(prefix="/topics", tags=["topics"])


@router.get("", response_model=list[schemas.TopicOut])
def list_topics(db: Session = Depends(get_db)):
    return db.query(models.Topic).all()


@router.post("", response_model=schemas.TopicOut)
def create_topic(payload: schemas.TopicCreate, db: Session = Depends(get_db)):
    topic = models.Topic(**payload.model_dump())
    db.add(topic)
    db.commit()
    db.refresh(topic)

    db.add(models.Mastery(topic_id=topic.id))
    db.commit()

    return topic


@router.post("/prerequisites")
def add_prerequisite(payload: schemas.PrerequisiteCreate, db: Session = Depends(get_db)):
    if payload.topic_id == payload.prerequisite_topic_id:
        raise HTTPException(status_code=400, detail="A topic cannot be its own prerequisite")

    existing = db.get(
        models.Prerequisite, (payload.topic_id, payload.prerequisite_topic_id)
    )
    if existing:
        raise HTTPException(status_code=400, detail="Prerequisite already exists")

    db.add(models.Prerequisite(**payload.model_dump()))
    db.commit()
    return {"status": "ok"}


@router.get("/graph/json")
def get_graph(db: Session = Depends(get_db)):
    return graph_service.get_graph_json(db)


@router.get("/graph/order", response_model=list[schemas.TopicOut])
def get_order(db: Session = Depends(get_db)):
    return graph_service.get_topic_order(db)


@router.get("/{topic_id}", response_model=schemas.TopicOut)
def get_topic(topic_id: int, db: Session = Depends(get_db)):
    topic = db.get(models.Topic, topic_id)
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")
    return topic
