from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.deps import get_current_user
from app.ownership import get_owned_course, get_owned_module, get_owned_topic
from app.services import graph_service, ordering

router = APIRouter(prefix="/topics", tags=["topics"])


@router.get("", response_model=list[schemas.TopicOut])
def list_topics(
    db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)
):
    return graph_service.topic_query(db, user_id=current_user.id).all()


@router.post("", response_model=schemas.TopicOut)
def create_topic(
    payload: schemas.TopicCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    module = get_owned_module(db, payload.module_id, current_user)

    topic = models.Topic(
        module_id=module.id,
        # topics.user_id is kept in sync with the course owner.
        user_id=module.course.user_id,
        name=payload.name,
        description=payload.description,
        position=ordering.next_position(module.topics),
    )
    db.add(topic)
    db.flush()
    db.add(models.Mastery(topic_id=topic.id))
    db.commit()
    db.refresh(topic)

    return topic


@router.post("/prerequisites")
def add_prerequisite(
    payload: schemas.PrerequisiteCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    if payload.topic_id == payload.prerequisite_topic_id:
        raise HTTPException(status_code=400, detail="A topic cannot be its own prerequisite")

    topic = get_owned_topic(db, payload.topic_id, current_user)
    prerequisite_topic = get_owned_topic(db, payload.prerequisite_topic_id, current_user)

    if topic.module.course_id != prerequisite_topic.module.course_id:
        raise HTTPException(
            status_code=400, detail="Prerequisites must be within the same course"
        )

    existing = db.get(
        models.Prerequisite, (payload.topic_id, payload.prerequisite_topic_id)
    )
    if existing:
        raise HTTPException(status_code=400, detail="Prerequisite already exists")

    # A prerequisite loop (A needs B, B needs A, or any longer circle) would leave
    # nothing to learn first and break the learning order, so it is refused. The
    # message shows the existing chain the new link would close into a circle.
    chain = graph_service.loop_path(
        db, current_user.id, payload.topic_id, payload.prerequisite_topic_id
    )
    if chain is not None:
        loop = " → ".join(chain + [chain[0]])
        raise HTTPException(
            status_code=400,
            detail=(
                f"That would create a loop ({loop}): "
                f"'{prerequisite_topic.name}' already depends on '{topic.name}'."
            ),
        )

    db.add(models.Prerequisite(**payload.model_dump()))
    db.commit()
    return {"status": "ok"}


@router.delete("/{topic_id}/prerequisites/{prerequisite_topic_id}", status_code=204)
def remove_prerequisite(
    topic_id: int,
    prerequisite_topic_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Remove the link that makes `prerequisite_topic_id` a prerequisite of
    `topic_id`. Both topics must be the caller's (404 otherwise, like every other
    route); 404 too when the link isn't there."""
    get_owned_topic(db, topic_id, current_user)
    get_owned_topic(db, prerequisite_topic_id, current_user)
    link = db.get(models.Prerequisite, (topic_id, prerequisite_topic_id))
    if link is None:
        raise HTTPException(status_code=404, detail="Prerequisite not found")
    db.delete(link)
    db.commit()
    return Response(status_code=204)


@router.get("/graph/json")
def get_graph(
    course_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    if course_id is not None:
        get_owned_course(db, course_id, current_user)
    return graph_service.get_graph_json(db, user_id=current_user.id, course_id=course_id)


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
    return get_owned_topic(db, topic_id, current_user)


@router.patch("/{topic_id}", response_model=schemas.TopicOut)
def update_topic(
    topic_id: int,
    payload: schemas.TopicUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    topic = get_owned_topic(db, topic_id, current_user)
    fields = payload.model_dump(exclude_unset=True)

    if fields.get("name") is not None:
        topic.name = fields["name"]
    if "description" in fields:
        topic.description = fields["description"]

    new_module_id = fields.get("module_id")
    if new_module_id is not None and new_module_id != topic.module_id:
        new_module = get_owned_module(db, new_module_id, current_user)
        old_module = topic.module
        if new_module.course_id != old_module.course_id:
            raise HTTPException(
                status_code=400, detail="A topic can only move to a module of the same course"
            )

        old_siblings = [t for t in old_module.topics if t.id != topic.id]
        topic.position = ordering.next_position(new_module.topics)
        topic.module = new_module
        topic.user_id = new_module.course.user_id
        ordering.repack(old_siblings)

    db.commit()
    db.refresh(topic)
    return topic


@router.delete("/{topic_id}", status_code=204)
def delete_topic(
    topic_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    topic = get_owned_topic(db, topic_id, current_user)
    siblings = [t for t in topic.module.topics if t.id != topic.id]
    # session.delete so mastery, sources/chunks, sessions, quiz questions and
    # prerequisite rows (as prerequisite or dependent) cascade through the ORM.
    db.delete(topic)
    ordering.repack(siblings)
    db.commit()
