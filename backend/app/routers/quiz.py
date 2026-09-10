from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.database import get_db
from app.routers.mastery import apply_score_delta
from app.services.quiz_service import generate_quiz

router = APIRouter(prefix="/quiz", tags=["quiz"])


@router.get("/{topic_id}", response_model=list[schemas.QuizQuestionOut])
def get_quiz(topic_id: int, db: Session = Depends(get_db)):
    topic = db.get(models.Topic, topic_id)
    if not topic:
        raise HTTPException(status_code=404, detail="Topic not found")

    existing = (
        db.query(models.QuizQuestion)
        .filter(models.QuizQuestion.topic_id == topic_id)
        .all()
    )
    if existing:
        return existing

    questions = [
        models.QuizQuestion(topic_id=topic_id, **stub) for stub in generate_quiz(topic.name)
    ]
    db.add_all(questions)
    db.commit()
    for question in questions:
        db.refresh(question)

    return questions


@router.post("/submit", response_model=schemas.QuizSubmitResult)
def submit_quiz(payload: schemas.QuizSubmitRequest, db: Session = Depends(get_db)):
    mastery = db.get(models.Mastery, payload.topic_id)
    if not mastery:
        raise HTTPException(status_code=404, detail="Mastery record not found")

    questions_by_id = {
        q.id: q
        for q in db.query(models.QuizQuestion)
        .filter(models.QuizQuestion.topic_id == payload.topic_id)
        .all()
    }

    correct = sum(
        1
        for answer in payload.answers
        if (question := questions_by_id.get(answer.question_id))
        and question.correct_option == answer.selected_option
    )

    total = len(payload.answers)
    score_percent = (correct / total * 100) if total else 0.0
    score_delta = round((score_percent - 50) / 5)

    db.add(
        models.StudySession(
            topic_id=payload.topic_id,
            type=models.SessionType.quiz,
            score_delta=score_delta,
        )
    )

    apply_score_delta(mastery, score_delta)

    db.commit()
    db.refresh(mastery)

    return schemas.QuizSubmitResult(
        total=total, correct=correct, score_percent=score_percent, mastery=mastery
    )
