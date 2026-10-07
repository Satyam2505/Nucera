"""Background quiz generation, one question at a time.

A CPU model takes minutes per question, so POST /quiz/{topic}/generate only
creates a QuizJob row and starts a worker thread; the page polls the row for
progress. The worker writes each question to the database the moment it is
validated, so a failure part-way keeps what was already written (as a "partial"
quiz) instead of throwing minutes of model time away.

The rule that a topic has at most one active job is the database's, not this
module's: a partial unique index over the active statuses makes the second
insert fail, whichever process it comes from. What the database can't know is
that a worker has died, so a job that stops reporting progress (or is still
marked active when the server starts) is closed off as interrupted, which frees
the topic.

The worker is a plain daemon thread in the API process: this is a personal,
single-user app with one server, and a thread needs no broker. `spawn` is the one
place that decides how the worker runs, so tests can run it inline.
"""

import logging
import random
import threading
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, load_only

from app import models
from app.config import QUIZ_JOB_STALE_SECONDS, QUIZ_MAX_EXCERPTS
from app.database import SessionLocal
from app.services import quiz_service
from app.services.quiz_service import (
    NO_MATERIAL_MESSAGE,
    NoMaterialError,
    QuizGenerationError,
    excerpt_char_budget,
    generate_question,
    select_excerpts,
    shuffle_options,
)

logger = logging.getLogger(__name__)

ACTIVE_STATUSES = ("queued", "running")
IN_PROGRESS_MESSAGE = "Quiz generation already in progress for this topic."
RESTART_MESSAGE = "The server restarted while this quiz was being written."
STALLED_MESSAGE = "The quiz generator stopped responding."
UNEXPECTED_MESSAGE = "Something went wrong while writing the quiz."


class GenerationInProgress(Exception):
    """The topic already has an active quiz job."""


def _now() -> datetime:
    return datetime.utcnow()


def _threaded(job_id: int) -> None:
    threading.Thread(target=run_job, args=(job_id,), name=f"quiz-job-{job_id}", daemon=True).start()


# Replaced in tests to run the worker inline.
spawn = _threaded


# --- finishing a job -----------------------------------------------------------------------------


def _finish(
    db: Session, job: models.QuizJob, quiz_set: Optional[models.QuizSet], reason: Optional[str]
) -> None:
    """Close a job and publish whatever it wrote.

    Every question written is kept: with at least one the set becomes a ready quiz
    (job "succeeded" if it is complete, "partial" if not); with none the empty set
    is removed and the job is "failed". `reason` explains a shortfall.
    """
    written = len(quiz_set.questions) if quiz_set is not None else 0
    if quiz_set is not None and written == 0:
        job.quiz_set_id = None
        db.flush()
        db.delete(quiz_set)
        quiz_set = None
    elif quiz_set is not None:
        quiz_set.status = "ready"

    if written >= job.requested:
        job.status, job.error = "succeeded", None
    elif written > 0:
        job.status = "partial"
        job.error = reason or f"Only {written} of {job.requested} questions could be written."
    else:
        job.status = "failed"
        job.error = reason or "No questions could be written."
    job.completed = written
    job.finished_at = job.heartbeat_at = _now()
    db.commit()


def _close_active(db: Session, job: models.QuizJob, reason: str) -> None:
    quiz_set = db.get(models.QuizSet, job.quiz_set_id) if job.quiz_set_id else None
    _finish(db, job, quiz_set, reason)


def fail_stale_jobs(db: Session, topic_id: Optional[int] = None, now: Optional[datetime] = None) -> int:
    """Close active jobs that have stopped reporting progress. Returns how many."""
    cutoff = (now or _now()) - timedelta(seconds=QUIZ_JOB_STALE_SECONDS)
    query = db.query(models.QuizJob).filter(models.QuizJob.status.in_(ACTIVE_STATUSES))
    if topic_id is not None:
        query = query.filter(models.QuizJob.topic_id == topic_id)
    closed = 0
    for job in query.all():
        if (job.heartbeat_at or job.created_at) < cutoff:
            _close_active(db, job, STALLED_MESSAGE)
            closed += 1
    return closed


def interrupt_active_jobs(db: Session) -> int:
    """At server start: no worker survives a restart, so every active job is dead."""
    closed = 0
    for job in db.query(models.QuizJob).filter(models.QuizJob.status.in_(ACTIVE_STATUSES)).all():
        _close_active(db, job, RESTART_MESSAGE)
        closed += 1
    return closed


# --- starting a job --------------------------------------------------------------------------------


def start_job(db: Session, topic: models.Topic, count: int) -> models.QuizJob:
    """Record a new job for `topic` and start its worker.

    Raises NoMaterialError (nothing to write a quiz from) or GenerationInProgress
    (the database refused a second active job for the topic).
    """
    if not quiz_service.topic_has_material(db, topic.id):
        raise NoMaterialError(NO_MATERIAL_MESSAGE)

    fail_stale_jobs(db, topic.id)
    job = models.QuizJob(
        topic_id=topic.id, status="queued", requested=count, completed=0, heartbeat_at=_now()
    )
    db.add(job)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise GenerationInProgress(IN_PROGRESS_MESSAGE)
    db.refresh(job)

    try:
        spawn(job.id)
    except Exception:
        logger.exception("Could not start the quiz worker for job %s", job.id)
        _close_active(db, job, UNEXPECTED_MESSAGE)
    return job


def active_job(db: Session, topic_id: int) -> Optional[models.QuizJob]:
    """The topic's queued or running job, after closing off any that went stale."""
    fail_stale_jobs(db, topic_id)
    return (
        db.query(models.QuizJob)
        .filter(models.QuizJob.topic_id == topic_id, models.QuizJob.status.in_(ACTIVE_STATUSES))
        .first()
    )


# --- the worker -----------------------------------------------------------------------------------------


def _alive(db: Session, job_id: int) -> bool:
    """Whether the job is still ours to run: its row exists (the topic wasn't
    deleted) and nothing has closed it (a stale sweep, a restart)."""
    status = db.query(models.QuizJob.status).filter(models.QuizJob.id == job_id).scalar()
    return status == "running"


def _beat(db: Session, job: models.QuizJob) -> None:
    job.heartbeat_at = _now()
    db.commit()


def run_job(job_id: int, rng: Optional[random.Random] = None) -> None:
    """Write the job's questions. Never raises; always leaves the job closed."""
    rng = rng or random.Random()
    db = SessionLocal()
    quiz_set: Optional[models.QuizSet] = None
    try:
        job = db.get(models.QuizJob, job_id)
        if job is None or job.status != "queued":
            return
        topic = db.get(models.Topic, job.topic_id)
        job.status = "running"
        job.started_at = _now()
        _beat(db, job)

        rows = (
            db.query(models.Chunk, models.Source.title)
            .options(
                # Excerpts need none of the 384 floats each chunk's embedding carries.
                load_only(
                    models.Chunk.id,
                    models.Chunk.source_id,
                    models.Chunk.chunk_text,
                    models.Chunk.chunk_index,
                    models.Chunk.page_number,
                )
            )
            .join(models.Source, models.Chunk.source_id == models.Source.id)
            .filter(models.Chunk.topic_id == topic.id)
            .all()
        )
        if not rows:
            _finish(db, job, None, NO_MATERIAL_MESSAGE)
            return
        chunks = [chunk for chunk, _ in rows]
        # Every commit below expires the session's objects; a chunk that expired would be
        # re-read whole, embedding included. Detached, the chunks keep what was loaded.
        for chunk in chunks:
            db.expunge(chunk)
        titles: Dict[int, str] = {chunk.source_id: title for chunk, title in rows}
        budget = excerpt_char_budget(topic.name, 1)

        quiz_set = models.QuizSet(topic_id=topic.id, status="generating")
        db.add(quiz_set)
        db.flush()
        job.quiz_set_id = quiz_set.id
        _beat(db, job)

        written: List[str] = []
        failure: Optional[str] = None
        unusable = 0
        for _slot in range(job.requested):
            if not _alive(db, job_id):
                return  # closed under us (topic deleted, restart sweep): don't write more
            job = db.get(models.QuizJob, job_id)
            quiz_set = db.get(models.QuizSet, job.quiz_set_id)
            excerpts = select_excerpts(chunks, titles, rng, max_excerpts=QUIZ_MAX_EXCERPTS, char_budget=budget)
            by_number = {e.number: e for e in excerpts}
            try:
                question = generate_question(topic.name, excerpts, written)
            except QuizGenerationError as exc:
                failure = str(exc)
                break
            if not _alive(db, job_id):
                return
            if question is None:
                unusable += 1
                continue

            question = shuffle_options(question, rng)
            # Citations come from the excerpts the question pointed at, never from
            # text the model wrote, so they can't be invented.
            cited: List[dict] = []
            for number in question.excerpt_numbers:
                ref = {"source": by_number[number].source, "page": by_number[number].page}
                if ref not in cited:
                    cited.append(ref)
            db.add(
                models.QuizQuestion(
                    quiz_set_id=quiz_set.id,
                    position=len(written),
                    question_text=question.question,
                    options=question.options,
                    correct_option=question.answer,
                    explanation=question.explanation,
                    sources=cited,
                )
            )
            written.append(question.question)
            job.completed = len(written)
            _beat(db, job)  # commits the question with the progress

        if failure is None and len(written) < job.requested:
            failure = (
                f"The local model didn't return a usable question for {unusable} of the "
                f"{job.requested} requested. Try again, or add more study material."
            )
        db.expire_all()
        job = db.get(models.QuizJob, job_id)  # re-read: the sweep may have closed it meanwhile
        if job is not None and job.status == "running":
            _finish(db, job, db.get(models.QuizSet, job.quiz_set_id), failure)
    except Exception:
        logger.exception("Quiz job %s failed", job_id)
        db.rollback()
        try:
            job = db.get(models.QuizJob, job_id)
            if job is not None and job.status in ACTIVE_STATUSES:
                _close_active(db, job, UNEXPECTED_MESSAGE)
        except Exception:
            logger.exception("Could not close quiz job %s after a failure", job_id)
            db.rollback()
    finally:
        db.close()
