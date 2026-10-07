from typing import Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app import models, schemas
from app.config import QUIZ_QUESTION_COUNT
from app.database import get_db
from app.deps import get_current_user
from app.ownership import get_owned_quiz_job, get_owned_quiz_set, get_owned_topic
from app.services import quiz_jobs, quiz_service
from app.services.mastery_service import apply_score_delta

router = APIRouter(prefix="/quiz", tags=["quiz"])

ALREADY_SUBMITTED = "This quiz was already submitted. Start a new quiz to try again."


def _has_attempt(quiz_set: models.QuizSet) -> bool:
    return bool(quiz_set.attempts)


def _question_out(question: models.QuizQuestion) -> schemas.QuizQuestionOut:
    return schemas.QuizQuestionOut.model_validate(question)


def _attempt_out(
    db: Session, quiz_set: models.QuizSet, attempt: models.QuizAttempt
) -> schemas.QuizAttemptOut:
    chosen_by_question: Dict[str, Optional[str]] = attempt.answers or {}
    results = []
    for question in quiz_set.questions:
        chosen = chosen_by_question.get(str(question.id))
        results.append(
            schemas.QuizResultItem(
                question_id=question.id,
                question_text=question.question_text,
                options=question.options,
                chosen=chosen,
                correct_option=question.correct_option,
                is_correct=chosen == question.correct_option,
                explanation=question.explanation,
                sources=[schemas.SourceCitation(**s) for s in (question.sources or [])],
            )
        )
    mastery = db.get(models.Mastery, quiz_set.topic_id)
    return schemas.QuizAttemptOut(
        id=attempt.id,
        quiz_set_id=quiz_set.id,
        correct=attempt.correct,
        total=attempt.total,
        score_percent=attempt.score_percent,
        score_delta=attempt.score_delta,
        created_at=attempt.created_at,
        results=results,
        mastery=schemas.MasteryOut.model_validate(mastery) if mastery else None,
    )


def _set_out(db: Session, quiz_set: models.QuizSet) -> schemas.QuizSetOut:
    # Answers and explanations only ever leave the server inside an attempt.
    attempt = quiz_set.attempts[-1] if quiz_set.attempts else None
    return schemas.QuizSetOut(
        id=quiz_set.id,
        topic_id=quiz_set.topic_id,
        created_at=quiz_set.created_at,
        questions=[_question_out(q) for q in quiz_set.questions],
        attempt=_attempt_out(db, quiz_set, attempt) if attempt else None,
    )


def _latest_ready_set(db: Session, topic_id: int) -> Optional[models.QuizSet]:
    return (
        db.query(models.QuizSet)
        .filter(models.QuizSet.topic_id == topic_id, models.QuizSet.status == "ready")
        .order_by(models.QuizSet.id.desc())
        .first()
    )


@router.get("/{topic_id}", response_model=schemas.QuizState)
def get_quiz(
    topic_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """The topic's latest quiz, if it has one, and its running generation, if any.
    This never generates: that is a slow, model-backed action and only POST
    .../generate starts it."""
    get_owned_topic(db, topic_id, current_user)
    latest = _latest_ready_set(db, topic_id)
    job = quiz_jobs.active_job(db, topic_id)
    return schemas.QuizState(
        quiz_set=_set_out(db, latest) if latest else None,
        has_material=quiz_service.topic_has_material(db, topic_id),
        job=schemas.QuizJobOut.model_validate(job) if job else None,
    )


@router.post("/{topic_id}/generate", response_model=schemas.QuizJobOut, status_code=202)
def generate_quiz(
    topic_id: int,
    count: int = Query(default=QUIZ_QUESTION_COUNT, ge=1, le=10),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Start writing a new quiz from the topic's study material, in the
    background, and return the job to poll (GET /quiz/jobs/{id}). When it
    finishes, the new set becomes the latest; earlier sets and their attempts are
    kept. 409 if there is nothing to write from or a job is already running."""
    topic = get_owned_topic(db, topic_id, current_user)
    try:
        job = quiz_jobs.start_job(db, topic, count)
    except (quiz_jobs.GenerationInProgress, quiz_service.NoMaterialError) as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    return schemas.QuizJobOut.model_validate(job)


@router.get("/jobs/{job_id}", response_model=schemas.QuizJobOut)
def get_quiz_job(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    job = get_owned_quiz_job(db, job_id, current_user)
    if job.status in quiz_jobs.ACTIVE_STATUSES:
        # A dead worker must not poll as "running" for ever.
        quiz_jobs.fail_stale_jobs(db, job.topic_id)
        db.refresh(job)
    return schemas.QuizJobOut.model_validate(job)


@router.get("/{topic_id}/history", response_model=List[schemas.QuizSummary])
def quiz_history(
    topic_id: int,
    limit: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """The topic's past quizzes, newest first: when, how many questions, and the
    result if it was taken. Questions and answers come from GET /quiz/sets/{id}."""
    get_owned_topic(db, topic_id, current_user)
    sets = (
        db.query(models.QuizSet)
        .filter(models.QuizSet.topic_id == topic_id, models.QuizSet.status == "ready")
        .order_by(models.QuizSet.id.desc())
        .limit(limit)
        .all()
    )
    summaries = []
    for quiz_set in sets:
        attempt = quiz_set.attempts[-1] if quiz_set.attempts else None
        summaries.append(
            schemas.QuizSummary(
                id=quiz_set.id,
                created_at=quiz_set.created_at,
                question_count=len(quiz_set.questions),
                taken=attempt is not None,
                correct=attempt.correct if attempt else None,
                total=attempt.total if attempt else None,
                score_percent=attempt.score_percent if attempt else None,
                attempted_at=attempt.created_at if attempt else None,
            )
        )
    return summaries


@router.get("/sets/{quiz_set_id}", response_model=schemas.QuizSetOut)
def get_quiz_set(
    quiz_set_id: int,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Any past quiz. As everywhere, the answers and explanations are only in
    the response once it has been graded."""
    return _set_out(db, get_owned_quiz_set(db, quiz_set_id, current_user))


@router.post("/submit", response_model=schemas.QuizAttemptOut)
def submit_quiz(
    payload: schemas.QuizSubmitRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    quiz_set = get_owned_quiz_set(db, payload.quiz_set_id, current_user)

    if not payload.answers:
        raise HTTPException(status_code=400, detail="Answer at least one question before submitting.")

    questions_by_id = {q.id: q for q in quiz_set.questions}
    chosen: Dict[int, str] = {}
    for answer in payload.answers:
        # One generic message for every kind of mismatch, so a rejected
        # submission reveals nothing about another quiz's questions or keys.
        if answer.question_id not in questions_by_id or answer.question_id in chosen:
            raise HTTPException(status_code=400, detail="Those answers don't match this quiz.")
        if answer.selected_option not in quiz_service.OPTION_KEYS:
            raise HTTPException(status_code=400, detail="Those answers don't match this quiz.")
        chosen[answer.question_id] = answer.selected_option

    if _has_attempt(quiz_set):
        raise HTTPException(status_code=409, detail=ALREADY_SUBMITTED)

    mastery = db.get(models.Mastery, quiz_set.topic_id)
    if not mastery:
        raise HTTPException(status_code=404, detail="Mastery record not found")

    # Unanswered questions count as wrong: the score is out of the whole set.
    total = len(questions_by_id)
    correct = sum(1 for qid, q in questions_by_id.items() if chosen.get(qid) == q.correct_option)
    score_percent = correct / total * 100
    score_delta = round((score_percent - 50) / 5)

    attempt = models.QuizAttempt(
        quiz_set_id=quiz_set.id,
        correct=correct,
        total=total,
        score_percent=score_percent,
        score_delta=score_delta,
        answers={str(qid): chosen.get(qid) for qid in questions_by_id},
    )
    quiz_set.attempts.append(attempt)
    db.add(
        models.StudySession(
            topic_id=quiz_set.topic_id, type=models.SessionType.quiz, score_delta=score_delta
        )
    )
    apply_score_delta(mastery, score_delta)

    try:
        db.commit()
    except IntegrityError:
        # A concurrent submit won the race for this set (the unique constraint
        # on quiz_attempts.quiz_set_id). Undo everything, including the
        # mastery change, and report the same conflict as the check above.
        db.rollback()
        raise HTTPException(status_code=409, detail=ALREADY_SUBMITTED)
    db.refresh(attempt)
    return _attempt_out(db, quiz_set, attempt)
