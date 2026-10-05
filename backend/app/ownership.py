"""Ownership lookups for the Course -> Module -> Topic hierarchy.

Ownership always resolves through course.user_id (topic -> module ->
course), never topics.user_id alone, and a resource someone else owns
looks exactly like one that doesn't exist (404). A NULL-owner course
(backfilled from pre-auth data) never matches any user.
"""

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app import models


def get_owned_course(db: Session, course_id: int, user: models.User) -> models.Course:
    course = (
        db.query(models.Course)
        .filter(models.Course.id == course_id, models.Course.user_id == user.id)
        .first()
    )
    if course is None:
        raise HTTPException(status_code=404, detail="Course not found")
    return course


def get_owned_module(db: Session, module_id: int, user: models.User) -> models.Module:
    module = (
        db.query(models.Module)
        .join(models.Course, models.Module.course_id == models.Course.id)
        .filter(models.Module.id == module_id, models.Course.user_id == user.id)
        .first()
    )
    if module is None:
        raise HTTPException(status_code=404, detail="Module not found")
    return module


def get_owned_topic(db: Session, topic_id: int, user: models.User) -> models.Topic:
    topic = (
        db.query(models.Topic)
        .join(models.Module, models.Topic.module_id == models.Module.id)
        .join(models.Course, models.Module.course_id == models.Course.id)
        .filter(models.Topic.id == topic_id, models.Course.user_id == user.id)
        .first()
    )
    if topic is None:
        raise HTTPException(status_code=404, detail="Topic not found")
    return topic


def get_owned_source(db: Session, source_id: int, user: models.User) -> models.Source:
    source = (
        db.query(models.Source)
        .join(models.Topic, models.Source.topic_id == models.Topic.id)
        .join(models.Module, models.Topic.module_id == models.Module.id)
        .join(models.Course, models.Module.course_id == models.Course.id)
        .filter(models.Source.id == source_id, models.Course.user_id == user.id)
        .first()
    )
    if source is None:
        raise HTTPException(status_code=404, detail="Source not found")
    return source
