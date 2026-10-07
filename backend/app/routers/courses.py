from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, selectinload

from app import models, schemas
from app.database import get_db
from app.deps import get_current_user
from app.ownership import get_owned_course, get_owned_module
from app.services import ordering, study_next

router = APIRouter(tags=["courses"])


def _with_tree_loaded(query):
    """One query per level (modules, topics, mastery) rather than one per row."""
    return query.options(
        selectinload(models.Course.modules)
        .selectinload(models.Module.topics)
        .selectinload(models.Topic.mastery)
    )


def _course_with_tree(db: Session, course_id: int) -> models.Course:
    return _with_tree_loaded(db.query(models.Course)).filter(models.Course.id == course_id).one()


def _to_tree(course: models.Course) -> schemas.CourseTree:
    return schemas.CourseTree(
        id=course.id,
        name=course.name,
        description=course.description,
        created_at=course.created_at,
        modules=[
            schemas.TreeModule(
                id=module.id,
                name=module.name,
                description=module.description,
                position=module.position,
                topics=[
                    schemas.TreeTopic(
                        id=topic.id,
                        name=topic.name,
                        description=topic.description,
                        position=topic.position,
                        status=(
                            topic.mastery.status
                            if topic.mastery
                            else models.MasteryStatus.unmastered
                        ),
                        score=topic.mastery.score if topic.mastery else 0,
                        flagged_for_revision=(
                            topic.mastery.flagged_for_revision if topic.mastery else False
                        ),
                    )
                    for topic in module.topics
                ],
            )
            for module in course.modules
        ],
    )


def _to_course_out(course: models.Course) -> schemas.CourseOut:
    topics = [topic for module in course.modules for topic in module.topics]
    scores = [topic.mastery.score if topic.mastery else 0 for topic in topics]
    return schemas.CourseOut(
        id=course.id,
        name=course.name,
        description=course.description,
        created_at=course.created_at,
        module_count=len(course.modules),
        topic_count=len(topics),
        avg_score=round(sum(scores) / len(scores)) if scores else 0,
    )


def _ensure_name_free(
    db: Session, user: models.User, name: str, exclude_course_id: Optional[int] = None
) -> None:
    query = db.query(models.Course).filter(
        models.Course.user_id == user.id, models.Course.name == name
    )
    if exclude_course_id is not None:
        query = query.filter(models.Course.id != exclude_course_id)
    if query.first():
        raise HTTPException(status_code=400, detail="A course with this name already exists")


@router.get("/courses", response_model=list[schemas.CourseOut])
def list_courses(
    db: Session = Depends(get_db), current_user: models.User = Depends(get_current_user)
):
    courses = (
        _with_tree_loaded(db.query(models.Course))
        .filter(models.Course.user_id == current_user.id)
        .order_by(models.Course.id)
        .all()
    )
    return [_to_course_out(course) for course in courses]


@router.post("/courses", response_model=schemas.CourseOut)
def create_course(
    payload: schemas.CourseCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    _ensure_name_free(db, current_user, payload.name)
    course = models.Course(
        user_id=current_user.id, name=payload.name, description=payload.description
    )
    db.add(course)
    db.commit()
    return _to_course_out(_course_with_tree(db, course.id))


@router.patch("/courses/{course_id}", response_model=schemas.CourseOut)
def update_course(
    course_id: int,
    payload: schemas.CourseUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    course = get_owned_course(db, course_id, current_user)
    fields = payload.model_dump(exclude_unset=True)

    if fields.get("name") is not None:
        _ensure_name_free(db, current_user, fields["name"], exclude_course_id=course.id)
        course.name = fields["name"]
    if "description" in fields:
        course.description = fields["description"]

    db.commit()
    return _to_course_out(_course_with_tree(db, course_id))


@router.delete("/courses/{course_id}", status_code=204)
def delete_course(
    course_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    course = get_owned_course(db, course_id, current_user)
    # session.delete (never a bulk delete) so the ORM cascades reach modules,
    # topics and everything hanging off them; SQLite doesn't enforce FK
    # cascades by default.
    db.delete(course)
    db.commit()


@router.get("/courses/{course_id}/tree", response_model=schemas.CourseTree)
def get_course_tree(
    course_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    get_owned_course(db, course_id, current_user)
    return _to_tree(_course_with_tree(db, course_id))


@router.post("/courses/{course_id}/modules", response_model=schemas.TreeModule)
def create_module(
    course_id: int,
    payload: schemas.ModuleCreate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    course = get_owned_course(db, course_id, current_user)
    module = models.Module(
        course_id=course.id,
        name=payload.name,
        description=payload.description,
        position=ordering.next_position(course.modules),
    )
    db.add(module)
    db.commit()
    db.refresh(module)
    return schemas.TreeModule(
        id=module.id,
        name=module.name,
        description=module.description,
        position=module.position,
        topics=[],
    )


@router.put("/courses/{course_id}/modules/order", response_model=schemas.CourseTree)
def reorder_modules(
    course_id: int,
    payload: schemas.OrderUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    course = get_owned_course(db, course_id, current_user)
    ordering.apply_order(course.modules, payload.ids)
    db.commit()
    return _to_tree(_course_with_tree(db, course_id))


@router.patch("/modules/{module_id}", response_model=schemas.CourseTree)
def update_module(
    module_id: int,
    payload: schemas.ModuleUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    module = get_owned_module(db, module_id, current_user)
    fields = payload.model_dump(exclude_unset=True)

    if fields.get("name") is not None:
        module.name = fields["name"]
    if "description" in fields:
        module.description = fields["description"]
    if fields.get("position") is not None:
        ordering.move_to_index(module.course.modules, module, fields["position"])

    course_id = module.course_id
    db.commit()
    return _to_tree(_course_with_tree(db, course_id))


@router.delete("/modules/{module_id}", status_code=204)
def delete_module(
    module_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    module = get_owned_module(db, module_id, current_user)
    siblings = [m for m in module.course.modules if m.id != module.id]
    # session.delete so the module's topics, their sources/chunks/mastery/
    # sessions/quiz questions and prerequisite rows go with it via the ORM
    # cascades.
    db.delete(module)
    ordering.repack(siblings)
    db.commit()


@router.put("/modules/{module_id}/topics/order", response_model=schemas.CourseTree)
def reorder_topics(
    module_id: int,
    payload: schemas.OrderUpdate,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    module = get_owned_module(db, module_id, current_user)
    ordering.apply_order(module.topics, payload.ids)
    course_id = module.course_id
    db.commit()
    return _to_tree(_course_with_tree(db, course_id))


@router.get("/courses/{course_id}/next", response_model=List[schemas.NextStepOut])
def what_to_study_next(
    course_id: int,
    limit: int = Query(default=3, ge=1, le=10),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """What to study next in the course, best first, each with the reason: topics due for
    review (learned but faded) first, then topics that are ready (not mastered, every
    prerequisite mastered). An empty list means everything is mastered and up to date."""
    get_owned_course(db, course_id, current_user)
    return study_next.next_steps(db, current_user.id, course_id, limit)
