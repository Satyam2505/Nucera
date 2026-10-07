"""Mastery that fades: the service functions (record_quiz, override_score, apply_score_delta),
the hook that shows the faded score whenever a row is loaded, and what the API, graph and
tutor see for a topic that has not been reviewed for a while. Numbers are worked out by
hand from services/mastery_model.py."""

from datetime import datetime, timedelta

import pytest
from sqlalchemy import text

from app import models
from app.services import graph_service, mastery_model
from app.services.mastery_service import apply_score_delta, override_score, record_quiz
from helpers import make_topic

T0 = datetime(2026, 10, 1, 12, 0, 0)


def days(n):
    return T0 + timedelta(days=n)


def bare(score=0, status=models.MasteryStatus.unmastered, **fields):
    """A mastery object that is not in a database (so no hook has run on it): `score` is
    what the student was shown, as it would be after a load."""
    return models.Mastery(topic_id=1, score=score, status=status, **fields)


def tracked(estimate, stability, reviewed, score, status):
    return bare(score=score, status=status, estimate=estimate, stability_days=stability, last_reviewed_at=reviewed)


# --- record_quiz ---------------------------------------------------------------------------------------


def test_a_first_quiz_on_a_new_topic():
    m = bare()
    delta = record_quiz(m, correct=3, total=3, now=T0)
    assert delta == 50 and m.score == 50 and m.status == models.MasteryStatus.in_progress
    assert m.estimate == pytest.approx(0.5) and m.stability_days == 3.0 and m.last_reviewed_at == T0


def test_a_long_perfect_quiz_is_worth_more_than_a_short_one():
    assert record_quiz(bare(), 1, 1, T0) == 25
    assert record_quiz(bare(), 5, 5, T0) == 62  # 0.625
    assert record_quiz(bare(), 10, 10, T0) == 77  # 10/13


def test_reviewing_a_faded_topic_the_proposals_worked_example():
    # Learned to 0.5 three days ago, so 25 is shown now. A perfect quiz of three.
    m = tracked(0.5, 3.0, T0, score=25, status=models.MasteryStatus.in_progress)
    delta = record_quiz(m, 3, 3, now=days(3))
    assert m.estimate == pytest.approx(0.75) and m.stability_days == pytest.approx(5.25)
    assert m.score == 75 and delta == 50 and m.last_reviewed_at == days(3)


def test_two_good_quizzes_in_a_row_reach_mastered():
    m = bare()
    record_quiz(m, 5, 5, T0)  # 62
    record_quiz(m, 5, 5, T0)  # estimate 0.375 x 0.625 + 0.625 = 0.859
    assert m.score == 86 and m.status == models.MasteryStatus.mastered


def test_a_failed_quiz_lowers_the_score_and_shortens_the_memory():
    m = tracked(0.8, 10.0, T0, score=80, status=models.MasteryStatus.mastered)
    delta = record_quiz(m, 0, 4, now=T0)  # weight 4/7
    assert m.estimate == pytest.approx(0.8 * 3 / 7) and m.stability_days == pytest.approx(6.0)
    assert m.score == 34 and delta == -46 and m.status == models.MasteryStatus.in_progress


def test_a_row_from_before_the_model_starts_from_its_stored_score():
    m = bare(score=40, status=models.MasteryStatus.in_progress)  # no estimate, no review history
    delta = record_quiz(m, 3, 3, T0)
    assert m.estimate == pytest.approx(0.7)  # 0.5 x 0.4 + 0.5 x 1
    assert m.score == 70 and delta == 30


def test_a_missed_topic_is_cleared_by_a_quiz_that_raises_it_and_not_by_one_that_does_not():
    up = tracked(0.4, 3.0, T0, score=40, status=models.MasteryStatus.missed)
    record_quiz(up, 3, 3, T0)
    assert up.score == 70 and up.status == models.MasteryStatus.in_progress

    down = tracked(0.4, 3.0, T0, score=40, status=models.MasteryStatus.missed)
    record_quiz(down, 0, 3, T0)
    assert down.score < 40 and down.status == models.MasteryStatus.missed


# --- override_score and apply_score_delta ----------------------------------------------------------------


def test_a_manual_score_is_a_fresh_review_at_that_level():
    m = tracked(0.5, 10.0, T0, score=25, status=models.MasteryStatus.in_progress)
    override_score(m, 90, now=days(5))
    assert (m.score, m.estimate, m.last_reviewed_at) == (90, 0.9, days(5))
    assert m.status == models.MasteryStatus.mastered
    assert m.stability_days == 10.0  # the half-life is kept


def test_a_manual_score_on_a_new_topic_starts_the_default_half_life():
    m = bare()
    override_score(m, 40, now=T0)
    assert (m.score, m.estimate, m.stability_days, m.last_reviewed_at) == (40, 0.4, 3.0, T0)


def test_a_manual_score_is_clamped():
    m = bare()
    override_score(m, 250, now=T0)
    assert m.score == 100 and m.estimate == 1.0
    override_score(m, -5, now=T0)
    assert m.score == 0 and m.estimate == 0.0


def test_a_self_report_moves_the_score_shown_now_by_exactly_that_much_without_a_review():
    m = tracked(0.5, 3.0, T0, score=25, status=models.MasteryStatus.in_progress)  # half faded
    apply_score_delta(m, 10, now=days(3))
    assert m.score == 35 and m.last_reviewed_at == T0  # not a review: the clock keeps running
    assert mastery_model.effective_score(m, days(3)) == 35
    assert m.estimate == pytest.approx(0.7)
    # ...and it keeps fading from there.
    assert mastery_model.effective_score(m, days(6)) == round(100 * 0.7 * 0.25)


def test_a_self_report_on_a_row_with_no_history_is_plain_arithmetic_as_before():
    m = bare(score=40, status=models.MasteryStatus.in_progress)
    apply_score_delta(m, -15, now=T0)
    assert m.score == 25 and m.last_reviewed_at is None and not m.estimate


def test_a_negative_self_report_cannot_go_below_zero():
    m = tracked(0.2, 3.0, T0, score=20, status=models.MasteryStatus.in_progress)
    apply_score_delta(m, -50, now=T0)
    assert m.score == 0 and m.estimate == 0.0 and m.status == models.MasteryStatus.unmastered


# --- the hook: a loaded row shows the faded score -----------------------------------------------------------


@pytest.fixture()
def topic(client):
    return make_topic(client, "Hash tables", course="DSA")


def set_history(db, topic_id, estimate, stability, age_days, status=models.MasteryStatus.mastered, stored_score=80):
    mastery = db.get(models.Mastery, topic_id)
    mastery.estimate, mastery.stability_days = estimate, stability
    mastery.last_reviewed_at = datetime.utcnow() - timedelta(days=age_days)
    mastery.score, mastery.status = stored_score, status
    db.commit()
    return mastery


def stored(db, topic_id):
    """What is actually in the database, bypassing the ORM (and so the hook)."""
    row = db.execute(text("SELECT score, status FROM mastery WHERE topic_id = :t"), {"t": topic_id}).one()
    return row[0], row[1]


def test_a_loaded_row_shows_the_faded_score_and_status(client, db_session, topic):
    set_history(db_session, topic["id"], 0.8, 3.0, age_days=3)
    db_session.expire_all()
    m = db_session.get(models.Mastery, topic["id"])
    assert m.score == 40 and m.status == models.MasteryStatus.in_progress  # 80 x 0.5: no longer mastered
    assert m.due_for_review is True


def test_the_hook_changes_what_is_shown_but_never_writes_it_back(client, db_session, topic):
    set_history(db_session, topic["id"], 0.8, 3.0, age_days=3)
    db_session.expire_all()
    m = db_session.get(models.Mastery, topic["id"])
    assert m.score == 40
    assert m not in db_session.dirty
    db_session.commit()
    assert stored(db_session, topic["id"]) == (80, "mastered")  # the database still has the score at the last review


def test_a_refresh_shows_the_faded_score_too(client, db_session, topic):
    m = set_history(db_session, topic["id"], 0.8, 3.0, age_days=3)
    db_session.refresh(m)
    assert m.score == 40


def test_a_row_with_no_history_is_shown_as_stored(client, db_session, topic):
    mastery = db_session.get(models.Mastery, topic["id"])
    mastery.score, mastery.status = 70, models.MasteryStatus.in_progress  # written without the model
    db_session.commit()
    db_session.expire_all()
    m = db_session.get(models.Mastery, topic["id"])
    assert (m.score, m.status, m.due_for_review) == (70, models.MasteryStatus.in_progress, False)


def test_missed_stays_missed_while_it_fades(client, db_session, topic):
    set_history(db_session, topic["id"], 0.8, 3.0, age_days=3, status=models.MasteryStatus.missed)
    db_session.expire_all()
    m = db_session.get(models.Mastery, topic["id"])
    assert m.score == 40 and m.status == models.MasteryStatus.missed


def test_a_topic_just_reviewed_has_not_faded(client, db_session, topic):
    set_history(db_session, topic["id"], 0.8, 3.0, age_days=0)
    db_session.expire_all()
    assert db_session.get(models.Mastery, topic["id"]).score == 80


# --- what the rest of the app sees --------------------------------------------------------------------------------


def test_the_mastery_api_reports_the_faded_score_and_that_it_is_due(client, db_session, topic):
    set_history(db_session, topic["id"], 0.8, 3.0, age_days=3)
    body = client.get(f"/mastery/{topic['id']}").json()
    assert body["score"] == 40 and body["status"] == "in_progress"
    assert body["due_for_review"] is True and body["last_reviewed_at"]
    listed = {m["topic_id"]: m for m in client.get("/mastery").json()}
    assert listed[topic["id"]]["score"] == 40


def test_a_new_topic_is_not_due_and_has_no_review_time(client, topic):
    body = client.get(f"/mastery/{topic['id']}").json()
    assert body["due_for_review"] is False and body["last_reviewed_at"] is None and body["score"] == 0


def test_the_graph_the_tree_and_the_course_average_all_show_the_faded_score(client, db_session, topic):
    set_history(db_session, topic["id"], 0.8, 3.0, age_days=3)
    node = next(n for n in client.get("/topics/graph/json").json()["nodes"] if n["id"] == topic["id"])
    assert (node["score"], node["status"]) == (40, "in_progress")
    tree_topic = client.get(f"/courses/{topic['course_id']}/tree").json()["modules"][0]["topics"][0]
    assert (tree_topic["score"], tree_topic["status"]) == (40, "in_progress")
    course = next(c for c in client.get("/courses").json() if c["id"] == topic["course_id"])
    assert course["avg_score"] == 40


def test_a_mastered_prerequisite_that_has_faded_is_flagged_again(client, db_session):
    base = make_topic(client, "Sets", course="Math")
    advanced = make_topic(client, "Functions", course="Math")
    client.post("/topics/prerequisites", json={"topic_id": advanced["id"], "prerequisite_topic_id": base["id"]})
    set_history(db_session, base["id"], 0.9, 3.0, age_days=0, stored_score=90)
    db_session.expire_all()
    assert graph_service.get_unmastered_prerequisites(db_session, advanced["id"], client.user_id) == []

    set_history(db_session, base["id"], 0.9, 3.0, age_days=3, stored_score=90)  # half faded: 45
    db_session.expire_all()
    flagged = graph_service.get_unmastered_prerequisites(db_session, advanced["id"], client.user_id)
    assert [t.name for t in flagged] == ["Sets"]


def test_putting_a_score_on_a_faded_topic_is_a_fresh_review(client, db_session, topic):
    set_history(db_session, topic["id"], 0.8, 3.0, age_days=3)
    body = client.put(f"/mastery/{topic['id']}", json={"score": 90}).json()
    assert body["score"] == 90 and body["status"] == "mastered" and body["due_for_review"] is False
    db_session.expire_all()
    assert db_session.get(models.Mastery, topic["id"]).score == 90  # and it stays 90: the clock restarted


def test_a_self_report_on_a_faded_topic_shifts_the_score_shown_and_keeps_it_due(client, db_session, topic):
    set_history(db_session, topic["id"], 0.8, 3.0, age_days=3)  # shows 40
    client.post("/sessions", json={"topic_id": topic["id"], "type": "self_report", "score_delta": 10})
    body = client.get(f"/mastery/{topic['id']}").json()
    assert body["score"] == 50 and body["due_for_review"] is True  # reporting is not reviewing


def test_a_graded_quiz_on_a_faded_topic_is_the_proposals_review_example(client, db_session, topic):
    set_history(db_session, topic["id"], 0.8, 3.0, age_days=3)  # shows 40
    quiz_set = models.QuizSet(topic_id=topic["id"])
    for position in range(5):
        quiz_set.questions.append(
            models.QuizQuestion(position=position, question_text=f"q{position}?", options={"A": "a", "B": "b", "C": "c", "D": "d"}, correct_option="A")
        )
    db_session.add(quiz_set)
    db_session.commit()
    answers = [{"question_id": q.id, "selected_option": "A"} for q in quiz_set.questions]

    body = client.post("/quiz/submit", json={"quiz_set_id": quiz_set.id, "answers": answers}).json()

    # estimate 0.375 x 0.8 + 0.625 = 0.925 -> 92 (92.5 rounds to even); it was showing 40.
    assert body["score_delta"] == 52 and body["mastery"]["score"] == 92
    assert body["mastery"]["status"] == "mastered" and body["mastery"]["due_for_review"] is False
    db_session.expire_all()
    m = db_session.get(models.Mastery, topic["id"])
    assert m.stability_days == pytest.approx(3.0 * (1 + 1.5 * 1.0 * (1 - 0.5)), rel=1e-3)  # 5.25


def test_decay_never_touches_the_chat_or_session_history(client, db_session, topic):
    set_history(db_session, topic["id"], 0.8, 3.0, age_days=30)
    assert client.get("/sessions").json() == []  # reading faded mastery recorded nothing
    assert db_session.query(models.StudySession).count() == 0
