"""Quiz endpoints: reading, background generation, grading, history, errors.

The model is mocked (as in the tutor tests) and chunks are inserted directly,
so none of this needs Ollama or the embedding model. The generation worker is a
thread in production; here it runs inline (see `inline_worker`), so a POST that
starts a job has finished it by the time the test looks.
"""

import json
from datetime import datetime, timedelta

import pytest
from sqlalchemy import event, func
from sqlalchemy.exc import IntegrityError

from app import models
from app.config import QUIZ_QUESTION_COUNT
from app.database import SessionLocal, engine
from app.routers import quiz as quiz_router
from app.services import llm_service, quiz_jobs
from helpers import make_topic


def make_q(n):
    return {
        "question": f"What does statement number {n} describe?",
        "options": {"A": f"Alpha {n}", "B": f"Bravo {n}", "C": f"Charlie {n}", "D": f"Delta {n}"},
        "answer": "A",
        "explanation": f"Explanation of fact {n}.",
        "sources": [1] if n % 2 else [1, 2],
    }


def one(n):
    """A model reply holding exactly one question, as each call now asks for."""
    return json.dumps({"questions": [make_q(n)]})


def replies(count):
    return [one(n) for n in range(1, count + 1)]


class FakeLLM:
    """Replies in order; the last one repeats. A reply can also be a callable taking
    the call number (run inside the worker, for mid-run assertions) or an LLMResult."""

    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = []

    def __call__(self, system_prompt, user_prompt, model=None, **kwargs):
        self.calls.append({"system": system_prompt, "user": user_prompt, **kwargs})
        reply = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        if callable(reply):
            reply = reply(len(self.calls))
        if isinstance(reply, llm_service.LLMResult):
            return reply
        return llm_service.LLMResult(ok=True, text=reply)


@pytest.fixture()
def fake_llm(monkeypatch):
    def install(*reply_list):
        fake = FakeLLM(*reply_list)
        monkeypatch.setattr(llm_service, "generate", fake)
        return fake

    return install


@pytest.fixture(autouse=True)
def inline_worker(monkeypatch):
    monkeypatch.setattr(quiz_jobs, "spawn", lambda job_id: quiz_jobs.run_job(job_id))


def add_material(db_session, topic_id):
    """Two sources, one chunk each (embeddings aren't needed for quizzes)."""
    for title, page, text in [
        ("Notes A", 3, "A hash table maps keys to values using a hash function."),
        ("Notes B", None, "Collisions are resolved with chaining or open addressing."),
    ]:
        source = models.Source(
            topic_id=topic_id, source_type=models.SourceType.self_supplied, title=title, raw_text=text
        )
        db_session.add(source)
        db_session.flush()
        db_session.add(
            models.Chunk(
                source_id=source.id, topic_id=topic_id, chunk_text=text, chunk_index=0, page_number=page
            )
        )
    db_session.commit()


@pytest.fixture()
def topic(client, db_session):
    made = make_topic(client, "Hash tables", course="DSA")
    add_material(db_session, made["id"])
    return made["id"]


def count(db_session, model):
    db_session.rollback()
    return db_session.query(func.count()).select_from(model).scalar()


def generate(client, topic_id, **params):
    return client.post(f"/quiz/{topic_id}/generate", params=params)


def run(client, topic_id, **params):
    """Start a job and return its final state (the worker ran inline)."""
    started = generate(client, topic_id, **params)
    assert started.status_code == 202, started.text
    job = client.get(f"/quiz/jobs/{started.json()['id']}")
    assert job.status_code == 200, job.text
    return job.json()


def current_set(client, topic_id):
    return client.get(f"/quiz/{topic_id}").json()["quiz_set"]


def keys_for(db_session, quiz_set_id):
    db_session.rollback()
    questions = (
        db_session.query(models.QuizQuestion)
        .filter(models.QuizQuestion.quiz_set_id == quiz_set_id)
        .order_by(models.QuizQuestion.position)
        .all()
    )
    return {q.id: q.correct_option for q in questions}


def wrong_option(correct):
    return "B" if correct != "B" else "C"


def answers(keys, correct_ids=(), wrong_ids=()):
    out = [{"question_id": qid, "selected_option": keys[qid]} for qid in correct_ids]
    out += [{"question_id": qid, "selected_option": wrong_option(keys[qid])} for qid in wrong_ids]
    return out


def add_job(db_session, topic_id, status="running", heartbeat_age=0, **fields):
    job = models.QuizJob(
        topic_id=topic_id,
        status=status,
        requested=3,
        completed=fields.pop("completed", 0),
        heartbeat_at=datetime.utcnow() - timedelta(seconds=heartbeat_age),
        **fields,
    )
    db_session.add(job)
    db_session.commit()
    return job


# --- reading (never generates) ---------------------------------------------------------


def test_get_without_a_set_returns_null_and_never_calls_the_model(client, topic, fake_llm):
    llm = fake_llm(one(1))
    resp = client.get(f"/quiz/{topic}")
    assert resp.status_code == 200
    assert resp.json() == {"quiz_set": None, "has_material": True, "job": None}
    assert llm.calls == []


def test_get_reports_when_there_is_no_material(client, fake_llm):
    llm = fake_llm(one(1))
    empty_topic = make_topic(client, "Empty", course="DSA")["id"]
    assert client.get(f"/quiz/{empty_topic}").json() == {"quiz_set": None, "has_material": False, "job": None}
    assert llm.calls == []


def test_get_never_creates_a_set_or_a_job_however_often_it_is_called(client, db_session, topic, fake_llm):
    llm = fake_llm(one(1))
    for _ in range(3):
        client.get(f"/quiz/{topic}")
    assert llm.calls == []
    assert count(db_session, models.QuizSet) == 0 and count(db_session, models.QuizJob) == 0


# --- generating: a background job, one question at a time ---------------------------------------


def test_generate_returns_a_job_at_once_with_the_default_of_three_questions(client, topic, fake_llm):
    fake_llm(*replies(3))
    resp = generate(client, topic)
    assert resp.status_code == 202
    body = resp.json()
    assert body["status"] == "queued" and body["requested"] == QUIZ_QUESTION_COUNT == 3
    assert body["completed"] == 0 and body["topic_id"] == topic
    assert set(body) == {
        "id", "topic_id", "status", "requested", "completed", "error",
        "created_at", "started_at", "finished_at",
    }


def test_the_worker_writes_one_question_per_model_call(client, db_session, topic, fake_llm):
    llm = fake_llm(*replies(3))
    job = run(client, topic)

    assert (job["status"], job["completed"], job["requested"], job["error"]) == ("succeeded", 3, 3, None)
    assert job["started_at"] and job["finished_at"]
    assert len(llm.calls) == 3
    for call in llm.calls:
        assert call["json_mode"] is True
        assert "Write 1 multiple-choice question." in call["user"]
        assert call["max_output_tokens"] < 500  # room for one question, not a whole quiz

    quiz_set = current_set(client, topic)
    assert [q["question_text"] for q in quiz_set["questions"]] == [make_q(n)["question"] for n in (1, 2, 3)]
    assert [q["position"] for q in quiz_set["questions"]] == [0, 1, 2]
    assert quiz_set["attempt"] is None


def test_neither_the_job_nor_the_quiz_leaks_answers_before_grading(client, topic, fake_llm):
    fake_llm(*replies(3))
    started = generate(client, topic)
    job = client.get(f"/quiz/jobs/{started.json()['id']}")
    state = client.get(f"/quiz/{topic}")
    for resp in (started, job, state):
        assert "correct_option" not in resp.text
        assert "Explanation of fact" not in resp.text
    for question in state.json()["quiz_set"]["questions"]:
        assert set(question) == {"id", "position", "question_text", "options"}


def test_each_question_after_the_first_is_told_what_was_already_written(client, topic, fake_llm):
    llm = fake_llm(*replies(3))
    run(client, topic)
    assert "already written" not in llm.calls[0]["user"]
    assert make_q(1)["question"] in llm.calls[1]["user"]
    assert make_q(1)["question"] in llm.calls[2]["user"] and make_q(2)["question"] in llm.calls[2]["user"]


def test_progress_is_stored_as_each_question_lands(client, db_session, topic, fake_llm):
    """A poll in the middle of a run sees the questions written so far."""
    seen = {}

    def peek(call_number):
        other = SessionLocal()
        try:
            job = other.query(models.QuizJob).one()
            seen[call_number] = (job.status, job.completed, job.heartbeat_at is not None)
            quiz_set = other.get(models.QuizSet, job.quiz_set_id)
            seen[f"set{call_number}"] = (quiz_set.status, len(quiz_set.questions))
        finally:
            other.close()
        return one(call_number)

    fake_llm(peek, peek, peek)
    run(client, topic)
    assert seen[1] == ("running", 0, True) and seen[2] == ("running", 1, True) and seen[3] == ("running", 2, True)
    # The set exists from the start, hidden as "generating", and grows one question at a time.
    assert seen["set1"] == ("generating", 0) and seen["set3"] == ("generating", 2)


def test_a_set_still_being_written_is_invisible_everywhere(client, db_session, topic, fake_llm):
    state = {}

    def look(call_number):
        state["latest"] = client.get(f"/quiz/{topic}").json()
        state["history"] = client.get(f"/quiz/{topic}/history").json()
        db_session.rollback()
        set_id = db_session.query(models.QuizSet.id).scalar()
        state["open"] = client.get(f"/quiz/sets/{set_id}").status_code
        state["grade"] = client.post(
            "/quiz/submit", json={"quiz_set_id": set_id, "answers": [{"question_id": 1, "selected_option": "A"}]}
        ).status_code
        return one(call_number)

    fake_llm(look, one(2), one(3))
    run(client, topic)
    assert state["latest"]["quiz_set"] is None
    assert state["latest"]["job"]["status"] == "running"
    assert state["history"] == [] and state["open"] == 404 and state["grade"] == 404
    assert current_set(client, topic) is not None  # and visible once finished


def test_the_finished_set_is_ready_and_a_reload_finds_no_active_job(client, db_session, topic, fake_llm):
    fake_llm(*replies(3))
    run(client, topic)
    state = client.get(f"/quiz/{topic}").json()
    assert state["job"] is None and len(state["quiz_set"]["questions"]) == 3
    db_session.rollback()
    assert db_session.query(models.QuizSet).one().status == "ready"


def test_generated_questions_keep_citations_built_from_the_excerpts(client, db_session, topic, fake_llm):
    fake_llm(*replies(3))
    run(client, topic)
    db_session.rollback()
    questions = db_session.query(models.QuizQuestion).order_by(models.QuizQuestion.position).all()
    assert questions[0].sources == [{"source": "Notes A", "page": 3}]  # cited only excerpt 1
    assert questions[1].sources == [{"source": "Notes A", "page": 3}, {"source": "Notes B", "page": None}]
    assert all(q.explanation for q in questions)


def test_excerpts_are_a_few_per_question_with_titles_and_pages(client, topic, fake_llm):
    llm = fake_llm(*replies(3))
    run(client, topic)
    assert "Notes A, p. 3" in llm.calls[0]["user"] and "Notes B" in llm.calls[0]["user"]


@pytest.mark.parametrize("count_param,expected", [(1, 1), (3, 3), (10, 10)])
def test_count_sets_how_many_questions_are_requested(client, topic, fake_llm, count_param, expected):
    llm = fake_llm(*replies(10))
    job = run(client, topic, count=count_param)
    assert job["requested"] == expected and job["completed"] == expected
    assert len(llm.calls) == expected


@pytest.mark.parametrize("bad", [0, -1, 11])
def test_count_outside_one_to_ten_is_rejected(client, topic, fake_llm, bad, db_session):
    llm = fake_llm(one(1))
    assert generate(client, topic, count=bad).status_code == 422
    assert llm.calls == [] and count(db_session, models.QuizJob) == 0


def test_no_material_is_a_409_and_the_model_is_never_called(client, db_session, fake_llm):
    llm = fake_llm(one(1))
    empty_topic = make_topic(client, "Empty", course="DSA")["id"]
    resp = generate(client, empty_topic)
    assert resp.status_code == 409
    assert "Add study material first" in resp.json()["detail"]
    assert llm.calls == []
    assert count(db_session, models.QuizSet) == 0 and count(db_session, models.QuizJob) == 0


# --- when the model misbehaves ---------------------------------------------------------------


def test_malformed_json_is_retried_within_the_same_question(client, topic, fake_llm):
    llm = fake_llm("{this is not json", one(1), one(2), one(3))
    job = run(client, topic)
    assert job["status"] == "succeeded" and job["completed"] == 3
    assert len(llm.calls) == 4


def test_a_question_the_model_cannot_get_right_is_skipped_and_the_next_gets_a_fresh_try(client, topic, fake_llm):
    bad = json.dumps({"questions": [{**make_q(9), "answer": "Z"}]})
    llm = fake_llm(one(1), bad, bad, one(3), one(4))
    job = run(client, topic)
    # Slot 2 failed both attempts; slot 3 worked: two questions, reported as partial.
    assert job["status"] == "partial" and job["completed"] == 2 and job["requested"] == 3
    assert "usable question for 1 of the 3" in job["error"]
    assert len(llm.calls) == 4
    assert [q["question_text"] for q in current_set(client, topic)["questions"]] == [
        make_q(1)["question"],
        make_q(3)["question"],
    ]


def test_a_repeat_of_an_earlier_question_is_not_stored_twice(client, db_session, topic, fake_llm):
    fake_llm(one(1), one(1), one(1), one(2), one(3))  # slot 2: the model only repeats itself, twice
    job = run(client, topic)
    assert job["completed"] == 2
    db_session.rollback()
    texts = [q.question_text for q in db_session.query(models.QuizQuestion).all()]
    assert len(texts) == len(set(texts))


def test_all_unusable_output_fails_the_job_and_stores_nothing(client, db_session, topic, fake_llm):
    llm = fake_llm("garbage")
    job = run(client, topic)
    assert job["status"] == "failed" and job["completed"] == 0
    assert "usable question" in job["error"]
    assert len(llm.calls) == 6  # three questions, two attempts each
    assert count(db_session, models.QuizSet) == 0 and count(db_session, models.QuizQuestion) == 0
    assert current_set(client, topic) is None


def test_ollama_down_fails_at_once_without_retries_or_leftovers(client, db_session, topic, fake_llm):
    llm = fake_llm(llm_service.LLMResult(ok=False, error="Ollama is not running or unreachable."))
    job = run(client, topic)
    assert job["status"] == "failed" and "Ollama is not running" in job["error"]
    assert len(llm.calls) == 1
    assert count(db_session, models.QuizSet) == 0
    assert job["finished_at"] is not None


def test_a_hiccup_inside_ollama_is_retried_and_the_quiz_still_completes(client, topic, fake_llm):
    hiccup = llm_service.LLMResult(ok=False, error="Ollama returned HTTP 500.", retryable=True)
    llm = fake_llm(one(1), hiccup, one(2), one(3))
    job = run(client, topic)
    assert job["status"] == "succeeded" and job["completed"] == 3
    assert len(llm.calls) == 4


def test_a_failure_after_some_questions_keeps_them_as_a_partial_quiz(client, db_session, topic, fake_llm):
    llm = fake_llm(one(1), one(2), llm_service.LLMResult(ok=False, error="The local model timed out."))
    job = run(client, topic)

    assert job["status"] == "partial" and job["completed"] == 2 and job["requested"] == 3
    assert "timed out" in job["error"]
    assert len(llm.calls) == 3
    quiz_set = current_set(client, topic)
    assert len(quiz_set["questions"]) == 2  # what was written survived the failure
    # ...and it is a real quiz: it can be graded.
    keys = keys_for(db_session, quiz_set["id"])
    graded = client.post(
        "/quiz/submit",
        json={"quiz_set_id": quiz_set["id"], "answers": answers(keys, correct_ids=list(keys))},
    )
    assert graded.status_code == 200 and graded.json()["total"] == 2


def test_the_worker_never_raises_and_always_closes_the_job(client, topic, fake_llm, monkeypatch):
    fake_llm(*replies(3))

    def boom(*args, **kwargs):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(quiz_jobs, "select_excerpts", boom)
    job = run(client, topic)
    assert job["status"] == "failed"
    assert "kaboom" not in json.dumps(job)  # no internals leak to the page
    assert job["error"] == quiz_jobs.UNEXPECTED_MESSAGE
    assert client.get(f"/quiz/{topic}").json()["job"] is None  # nothing left "running"


def test_a_worker_that_cannot_start_closes_the_job_instead_of_leaving_it_queued(client, topic, monkeypatch):
    def no_threads(job_id):
        raise RuntimeError("can't start new thread")

    monkeypatch.setattr(quiz_jobs, "spawn", no_threads)
    started = generate(client, topic)
    assert started.status_code == 202
    job = client.get(f"/quiz/jobs/{started.json()['id']}").json()
    assert job["status"] == "failed" and job["error"] == quiz_jobs.UNEXPECTED_MESSAGE
    assert generate(client, topic).status_code == 202  # the topic is not stuck


def test_in_production_the_worker_runs_on_its_own_thread(monkeypatch):
    import threading

    ran = {}
    done = threading.Event()

    def fake_run(job_id):
        ran["job"], ran["thread"] = job_id, threading.current_thread()
        done.set()

    monkeypatch.setattr(quiz_jobs, "run_job", fake_run)
    quiz_jobs._threaded(42)
    assert done.wait(timeout=5)
    assert ran["job"] == 42
    assert ran["thread"] is not threading.main_thread() and ran["thread"].daemon


# --- one active job per topic, enforced by the database ---------------------------------------------


def test_a_second_generation_while_one_is_active_is_a_409(client, db_session, topic, fake_llm):
    llm = fake_llm(*replies(3))
    add_job(db_session, topic, status="running")
    resp = generate(client, topic)
    assert resp.status_code == 409
    assert "already in progress" in resp.json()["detail"]
    assert llm.calls == []
    assert count(db_session, models.QuizJob) == 1


def test_a_queued_job_blocks_too(client, db_session, topic, fake_llm):
    fake_llm(*replies(3))
    add_job(db_session, topic, status="queued")
    assert generate(client, topic).status_code == 409


def test_the_guard_is_a_database_constraint_not_application_state(db_session, topic):
    add_job(db_session, topic, status="running")
    db_session.add(models.QuizJob(topic_id=topic, status="queued", requested=3))
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
    assert count(db_session, models.QuizJob) == 1


def test_a_request_that_loses_the_race_for_the_slot_is_a_409(client, db_session, topic, fake_llm, monkeypatch):
    """Both requests pass any check; only one insert can succeed."""
    fake_llm(*replies(3))
    add_job(db_session, topic, status="running")
    monkeypatch.setattr(quiz_jobs, "fail_stale_jobs", lambda *a, **k: 0)
    monkeypatch.setattr(quiz_jobs, "active_job", lambda *a, **k: None)  # nothing visible to a pre-check
    assert generate(client, topic).status_code == 409
    assert count(db_session, models.QuizJob) == 1


def test_finished_jobs_do_not_block_and_other_topics_are_independent(client, db_session, topic, fake_llm):
    fake_llm(*replies(10))
    other = make_topic(client, "Other", course="DSA")["id"]
    add_material(db_session, other)
    add_job(db_session, topic, status="running")
    assert run(client, other)["status"] == "succeeded"  # a different topic is unaffected

    db_session.query(models.QuizJob).filter(models.QuizJob.topic_id == topic).update({"status": "failed"})
    db_session.commit()
    assert run(client, topic)["status"] == "succeeded"
    assert run(client, topic)["status"] == "succeeded"  # and again: nothing active remains


def test_a_get_reports_the_active_job_so_a_reload_can_resume_its_progress(client, db_session, topic):
    job = add_job(db_session, topic, status="running", completed=1)
    state = client.get(f"/quiz/{topic}").json()
    assert state["job"]["id"] == job.id
    assert (state["job"]["status"], state["job"]["completed"], state["job"]["requested"]) == ("running", 1, 3)


# --- dead workers ---------------------------------------------------------------------------------------


def test_a_job_that_stopped_reporting_is_closed_and_no_longer_blocks(client, db_session, topic, fake_llm):
    fake_llm(*replies(3))
    stale = add_job(db_session, topic, status="running", heartbeat_age=quiz_jobs.QUIZ_JOB_STALE_SECONDS + 60)
    job = run(client, topic)  # starting a new one first closes the dead one
    assert job["status"] == "succeeded"
    db_session.rollback()
    old = db_session.get(models.QuizJob, stale.id)
    assert old.status == "failed" and old.error == quiz_jobs.STALLED_MESSAGE


def test_a_job_with_a_recent_heartbeat_is_left_alone(client, db_session, topic, fake_llm):
    fake_llm(*replies(3))
    add_job(db_session, topic, status="running", heartbeat_age=quiz_jobs.QUIZ_JOB_STALE_SECONDS - 120)
    assert generate(client, topic).status_code == 409


def test_polling_a_dead_job_reports_it_failed_not_running_forever(client, db_session, topic):
    stale = add_job(db_session, topic, status="running", heartbeat_age=quiz_jobs.QUIZ_JOB_STALE_SECONDS + 60)
    polled = client.get(f"/quiz/jobs/{stale.id}").json()
    assert polled["status"] == "failed" and polled["error"] == quiz_jobs.STALLED_MESSAGE


def test_a_restart_closes_every_active_job_but_keeps_the_questions_already_written(client, db_session, topic):
    quiz_set = models.QuizSet(topic_id=topic, status="generating")
    quiz_set.questions.append(
        models.QuizQuestion(position=0, question_text="written before the crash", options={"A": "a"}, correct_option="A")
    )
    db_session.add(quiz_set)
    db_session.commit()
    add_job(db_session, topic, status="running", completed=1, quiz_set_id=quiz_set.id)

    empty_topic = make_topic(client, "Empty run", course="DSA")["id"]
    empty_set = models.QuizSet(topic_id=empty_topic, status="generating")
    db_session.add(empty_set)
    db_session.commit()
    add_job(db_session, empty_topic, status="queued", quiz_set_id=empty_set.id)
    kept_set_id, empty_set_id = quiz_set.id, empty_set.id

    db = SessionLocal()
    try:
        assert quiz_jobs.interrupt_active_jobs(db) == 2
    finally:
        db.close()

    db_session.expire_all()
    kept, lost = db_session.query(models.QuizJob).order_by(models.QuizJob.id).all()
    assert kept.status == "partial" and kept.completed == 1 and kept.error == quiz_jobs.RESTART_MESSAGE
    assert lost.status == "failed" and lost.quiz_set_id is None
    assert db_session.get(models.QuizSet, kept_set_id).status == "ready"
    assert db_session.get(models.QuizSet, empty_set_id) is None  # an empty set is not left behind
    assert current_set(client, topic)["questions"][0]["question_text"] == "written before the crash"


def test_starting_the_server_closes_jobs_left_running(db_session, topic, caplog):
    import logging

    from fastapi.testclient import TestClient

    from app.main import app

    add_job(db_session, topic, status="running")
    with caplog.at_level(logging.WARNING, logger="uvicorn.error"):
        with TestClient(app):  # entering the context runs the startup hook
            pass
    db_session.expire_all()
    assert db_session.query(models.QuizJob).one().status == "failed"
    assert "quiz generation job" in caplog.text


# --- topics going away mid-run -------------------------------------------------------------------------------


def test_deleting_the_topic_while_a_quiz_is_being_written_leaves_nothing_behind(client, db_session, topic, fake_llm):
    def delete_topic(call_number):
        other = SessionLocal()
        try:
            other.delete(other.get(models.Topic, topic))
            other.commit()
        finally:
            other.close()
        return one(call_number)

    llm = fake_llm(delete_topic, one(2), one(3))
    generate(client, topic)
    assert len(llm.calls) == 1  # the worker noticed and stopped writing
    for model in (models.QuizQuestion, models.QuizSet, models.QuizJob):
        assert count(db_session, model) == 0


# --- history and past quizzes -------------------------------------------------------------------------------------


def test_history_lists_past_quizzes_newest_first_with_their_results(client, db_session, topic, fake_llm):
    fake_llm(*replies(10))
    run(client, topic, count=2)
    first = current_set(client, topic)
    keys = keys_for(db_session, first["id"])
    client.post(
        "/quiz/submit",
        json={"quiz_set_id": first["id"], "answers": answers(keys, correct_ids=list(keys)[:1], wrong_ids=list(keys)[1:])},
    )
    run(client, topic, count=3)
    second = current_set(client, topic)

    history = client.get(f"/quiz/{topic}/history").json()
    assert [h["id"] for h in history] == [second["id"], first["id"]]
    newest, oldest = history
    assert (newest["question_count"], newest["taken"], newest["correct"], newest["score_percent"]) == (3, False, None, None)
    assert newest["attempted_at"] is None and newest["created_at"]
    assert (oldest["question_count"], oldest["taken"], oldest["correct"], oldest["total"]) == (2, True, 1, 2)
    assert oldest["score_percent"] == 50.0 and oldest["attempted_at"]


def test_history_has_no_questions_or_answers(client, topic, fake_llm):
    fake_llm(*replies(3))
    run(client, topic)
    resp = client.get(f"/quiz/{topic}/history")
    for secret in ("question_text", "options", "correct_option", "Explanation of fact", "Alpha"):
        assert secret not in resp.text


def test_history_limit(client, topic, fake_llm):
    fake_llm(*replies(10))
    for _ in range(3):
        run(client, topic, count=1)
    assert len(client.get(f"/quiz/{topic}/history", params={"limit": 2}).json()) == 2
    assert client.get(f"/quiz/{topic}/history", params={"limit": 0}).status_code == 422


def test_a_past_untaken_quiz_can_be_opened_and_still_hides_its_answers(client, topic, fake_llm):
    fake_llm(*replies(10))
    run(client, topic, count=2)
    old = current_set(client, topic)
    run(client, topic, count=2)

    opened = client.get(f"/quiz/sets/{old['id']}")
    assert opened.status_code == 200
    assert opened.json()["attempt"] is None and len(opened.json()["questions"]) == 2
    assert "correct_option" not in opened.text and "Explanation of fact" not in opened.text


def test_a_past_taken_quiz_shows_its_results(client, db_session, topic, fake_llm):
    fake_llm(*replies(10))
    run(client, topic, count=2)
    old = current_set(client, topic)
    keys = keys_for(db_session, old["id"])
    client.post("/quiz/submit", json={"quiz_set_id": old["id"], "answers": answers(keys, correct_ids=list(keys))})
    run(client, topic, count=2)  # the old quiz is no longer the latest

    opened = client.get(f"/quiz/sets/{old['id']}").json()
    assert opened["attempt"]["correct"] == 2 and opened["attempt"]["results"][0]["explanation"]


def test_a_past_untaken_quiz_can_still_be_taken(client, db_session, topic, fake_llm):
    fake_llm(*replies(10))
    run(client, topic, count=2)
    old = current_set(client, topic)
    run(client, topic, count=2)
    keys = keys_for(db_session, old["id"])
    graded = client.post("/quiz/submit", json={"quiz_set_id": old["id"], "answers": answers(keys, correct_ids=list(keys))})
    assert graded.status_code == 200


# --- grading ---------------------------------------------------------------------------------------


@pytest.fixture()
def quiz(client, db_session, topic, fake_llm):
    fake_llm(*replies(5))
    run(client, topic, count=5)
    created = current_set(client, topic)
    return {
        "topic": topic,
        "set": created["id"],
        "ids": [q["id"] for q in created["questions"]],
        "keys": keys_for(db_session, created["id"]),
    }


def submit(client, quiz, answer_list):
    return client.post("/quiz/submit", json={"quiz_set_id": quiz["set"], "answers": answer_list})


def test_a_perfect_submission_scores_100_and_raises_mastery(client, db_session, quiz):
    resp = submit(client, quiz, answers(quiz["keys"], correct_ids=quiz["ids"]))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert (body["correct"], body["total"], body["score_percent"], body["score_delta"]) == (5, 5, 100.0, 10)
    assert all(r["is_correct"] for r in body["results"])
    assert body["mastery"]["score"] == 10 and body["mastery"]["status"] == "in_progress"
    assert count(db_session, models.QuizAttempt) == 1
    sessions = db_session.query(models.StudySession).all()
    assert [(s.type, s.score_delta) for s in sessions] == [(models.SessionType.quiz, 10)]


def test_results_carry_the_key_the_choice_the_explanation_and_citations(client, quiz):
    first, second = quiz["ids"][0], quiz["ids"][1]
    answer_list = answers(quiz["keys"], correct_ids=[first], wrong_ids=[second])
    body = submit(client, quiz, answer_list).json()
    by_id = {r["question_id"]: r for r in body["results"]}

    assert [r["question_id"] for r in body["results"]] == quiz["ids"]  # question order
    ok, bad = by_id[first], by_id[second]
    assert ok["is_correct"] is True and ok["chosen"] == ok["correct_option"] == quiz["keys"][first]
    assert ok["explanation"] == "Explanation of fact 1."
    assert ok["sources"] == [{"source": "Notes A", "page": 3, "topic": None}]
    assert bad["is_correct"] is False and bad["chosen"] == wrong_option(quiz["keys"][second])
    assert bad["correct_option"] == quiz["keys"][second]
    assert bad["sources"] == [
        {"source": "Notes A", "page": 3, "topic": None},
        {"source": "Notes B", "page": None, "topic": None},
    ]
    assert sorted(bad["options"]) == ["A", "B", "C", "D"]


def test_unanswered_questions_count_as_wrong(client, quiz):
    # 3 correct answers out of 5 questions, 2 left blank -> 60%, delta +2.
    body = submit(client, quiz, answers(quiz["keys"], correct_ids=quiz["ids"][:3])).json()
    assert (body["correct"], body["total"], body["score_percent"], body["score_delta"]) == (3, 5, 60.0, 2)
    unanswered = [r for r in body["results"] if r["chosen"] is None]
    assert len(unanswered) == 2 and not any(r["is_correct"] for r in unanswered)


def test_all_wrong_lowers_the_score_but_never_below_zero(client, quiz):
    body = submit(client, quiz, answers(quiz["keys"], wrong_ids=quiz["ids"])).json()
    assert (body["correct"], body["score_percent"], body["score_delta"]) == (0, 0.0, -10)
    assert body["mastery"]["score"] == 0 and body["mastery"]["status"] == "unmastered"


def test_an_empty_submission_is_a_400(client, db_session, quiz):
    resp = submit(client, quiz, [])
    assert resp.status_code == 400
    assert count(db_session, models.QuizAttempt) == 0


@pytest.mark.parametrize(
    "bad_answer",
    [
        {"question_id": 999999, "selected_option": "A"},  # not in this set
        {"question_id": 0, "selected_option": "A"},
    ],
)
def test_an_unknown_question_id_is_a_400(client, quiz, bad_answer):
    resp = submit(client, quiz, [bad_answer])
    assert resp.status_code == 400
    assert resp.json() == {"detail": "Those answers don't match this quiz."}


@pytest.mark.parametrize("option", ["E", "a", "", "AB", "Alpha"])
def test_an_option_outside_A_to_D_is_a_400(client, db_session, quiz, option):
    resp = submit(client, quiz, [{"question_id": quiz["ids"][0], "selected_option": option}])
    assert resp.status_code == 400
    assert count(db_session, models.QuizAttempt) == 0


def test_answering_the_same_question_twice_is_a_400(client, quiz):
    qid = quiz["ids"][0]
    resp = submit(client, quiz, [
        {"question_id": qid, "selected_option": "A"},
        {"question_id": qid, "selected_option": "B"},
    ])
    assert resp.status_code == 400


def test_a_set_can_only_be_graded_once(client, db_session, quiz):
    assert submit(client, quiz, answers(quiz["keys"], correct_ids=quiz["ids"])).status_code == 200
    again = submit(client, quiz, answers(quiz["keys"], correct_ids=quiz["ids"]))
    assert again.status_code == 409
    assert "already submitted" in again.json()["detail"]
    assert count(db_session, models.QuizAttempt) == 1
    assert client.get(f"/mastery/{quiz['topic']}").json()["score"] == 10  # not farmed


def test_the_graded_set_shows_its_results_on_reload_but_the_ungraded_one_hides_them(client, quiz):
    before = client.get(f"/quiz/{quiz['topic']}").json()["quiz_set"]
    assert before["attempt"] is None
    assert "explanation" not in json.dumps(before) and "correct_option" not in json.dumps(before)

    submit(client, quiz, answers(quiz["keys"], correct_ids=quiz["ids"][:2]))
    after = client.get(f"/quiz/{quiz['topic']}").json()["quiz_set"]
    assert after["attempt"]["correct"] == 2
    assert len(after["attempt"]["results"]) == 5
    assert after["attempt"]["results"][0]["explanation"]


def test_one_attempt_per_set_is_a_database_guarantee(db_session, quiz):
    def attempt():
        return models.QuizAttempt(
            quiz_set_id=quiz["set"], correct=1, total=5, score_percent=20.0, score_delta=-6, answers={}
        )

    db_session.add(attempt())
    db_session.commit()
    db_session.add(attempt())
    with pytest.raises(IntegrityError):
        db_session.commit()
    db_session.rollback()
    assert count(db_session, models.QuizAttempt) == 1


def test_a_submit_that_loses_the_race_is_a_409_and_changes_nothing(
    client, db_session, quiz, monkeypatch
):
    # Another request already recorded an attempt for this set...
    db_session.add(
        models.QuizAttempt(
            quiz_set_id=quiz["set"], correct=5, total=5, score_percent=100.0, score_delta=10, answers={}
        )
    )
    db_session.commit()
    # ...but this request's "already submitted" check ran before that commit and
    # passed. The unique constraint must still stop it.
    monkeypatch.setattr(quiz_router, "_has_attempt", lambda quiz_set: False)

    resp = submit(client, quiz, answers(quiz["keys"], correct_ids=quiz["ids"]))
    assert resp.status_code == 409
    assert "already submitted" in resp.json()["detail"]

    assert count(db_session, models.QuizAttempt) == 1
    assert count(db_session, models.StudySession) == 0  # no second session was recorded
    assert client.get(f"/mastery/{quiz['topic']}").json()["score"] == 0  # delta not applied


def test_resubmitting_an_attempted_set_is_a_409_and_changes_nothing(client, db_session, quiz):
    db_session.add(
        models.QuizAttempt(
            quiz_set_id=quiz["set"], correct=5, total=5, score_percent=100.0, score_delta=10, answers={}
        )
    )
    db_session.commit()

    resp = submit(client, quiz, answers(quiz["keys"], correct_ids=quiz["ids"]))
    assert resp.status_code == 409
    assert count(db_session, models.QuizAttempt) == 1
    assert count(db_session, models.StudySession) == 0
    assert client.get(f"/mastery/{quiz['topic']}").json()["score"] == 0


def test_generation_does_not_load_chunk_embeddings(client, topic, fake_llm):
    fake_llm(*replies(3))
    statements = []

    def record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    try:
        assert run(client, topic)["status"] == "succeeded"
    finally:
        event.remove(engine, "before_cursor_execute", record)

    chunk_selects = [s for s in statements if "FROM chunks" in s and s.lstrip().startswith("SELECT")]
    assert chunk_selects
    offenders = [s for s in chunk_selects if "chunks.embedding" in s]
    assert not offenders, offenders[0][:300]


# --- regeneration keeps history --------------------------------------------------------------------


def test_regenerating_adds_a_new_set_and_keeps_old_sets_and_attempts(client, db_session, topic, fake_llm, quiz):
    submit(client, quiz, answers(quiz["keys"], correct_ids=quiz["ids"]))
    old_questions = count(db_session, models.QuizQuestion)

    fake_llm(*replies(3))
    run(client, topic, count=3)
    new = current_set(client, topic)
    assert new["id"] != quiz["set"]
    assert new["attempt"] is None

    assert count(db_session, models.QuizSet) == 2
    assert count(db_session, models.QuizAttempt) == 1  # the earlier attempt survives
    assert count(db_session, models.QuizQuestion) == old_questions + 3
    assert count(db_session, models.QuizJob) == 2

    # The new set can be graded in its own right.
    new_keys = keys_for(db_session, new["id"])
    graded = client.post(
        "/quiz/submit",
        json={"quiz_set_id": new["id"], "answers": answers(new_keys, correct_ids=list(new_keys))},
    )
    assert graded.status_code == 200
    assert count(db_session, models.QuizAttempt) == 2


# --- cross-user ----------------------------------------------------------------------------------------


def test_other_users_cannot_read_generate_or_grade_my_quiz(client, other_client, db_session, quiz, fake_llm):
    llm = fake_llm(one(1))
    jobs_before = count(db_session, models.QuizJob)
    assert other_client.get(f"/quiz/{quiz['topic']}").status_code == 404
    assert other_client.post(f"/quiz/{quiz['topic']}/generate").status_code == 404
    assert other_client.get(f"/quiz/{quiz['topic']}/history").status_code == 404
    assert other_client.get(f"/quiz/sets/{quiz['set']}").status_code == 404
    resp = other_client.post(
        "/quiz/submit",
        json={"quiz_set_id": quiz["set"], "answers": answers(quiz["keys"], correct_ids=quiz["ids"])},
    )
    assert resp.status_code == 404
    assert llm.calls == []
    assert count(db_session, models.QuizJob) == jobs_before


def test_other_users_cannot_see_my_job(client, other_client, topic, fake_llm):
    fake_llm(*replies(3))
    job = run(client, topic)
    assert other_client.get(f"/quiz/jobs/{job['id']}").status_code == 404
    assert other_client.get("/quiz/jobs/999999").status_code == 404


def test_someone_elses_question_ids_against_my_own_set_get_a_400_that_leaks_nothing(
    client, other_client, db_session, quiz
):
    # B has a quiz of their own...
    b_topic = make_topic(other_client, "B topic", course="B course")["id"]
    b_set = models.QuizSet(topic_id=b_topic)
    b_set.questions.append(
        models.QuizQuestion(
            position=0,
            question_text="B's question",
            options={"A": "1", "B": "2", "C": "3", "D": "4"},
            correct_option="C",
            explanation="B's secret explanation",
        )
    )
    db_session.add(b_set)
    db_session.commit()
    b_set_id = b_set.id

    # ...and submits A's question ids against it.
    resp = other_client.post(
        "/quiz/submit",
        json={"quiz_set_id": b_set_id, "answers": answers(quiz["keys"], correct_ids=quiz["ids"])},
    )
    assert resp.status_code == 400
    assert resp.json() == {"detail": "Those answers don't match this quiz."}
    for secret in ("explanation", "Explanation of fact", "correct", "Alpha", "Notes A"):
        assert secret not in resp.text

    db_session.rollback()
    assert db_session.query(models.QuizAttempt).count() == 0
    assert other_client.get(f"/mastery/{b_topic}").json()["score"] == 0
    # And A's set is untouched: still ungraded and gradable.
    assert submit(client, quiz, answers(quiz["keys"], correct_ids=quiz["ids"])).status_code == 200


def test_questions_of_one_set_cannot_be_submitted_against_another_of_my_sets(client, db_session, topic, fake_llm, quiz):
    fake_llm(*replies(3))
    run(client, topic, count=3)
    other_set = current_set(client, topic)
    resp = client.post(
        "/quiz/submit",
        json={
            "quiz_set_id": other_set["id"],
            "answers": answers(quiz["keys"], correct_ids=quiz["ids"][:1]),
        },
    )
    assert resp.status_code == 400
    assert count(db_session, models.QuizAttempt) == 0


# --- a worker closed from outside stops writing ---------------------------------------------------------


def test_a_job_closed_by_a_sweep_mid_run_stops_the_worker_and_keeps_what_was_written(
    client, db_session, topic, fake_llm
):
    def sweep_during_second_call(call_number):
        db = SessionLocal()
        try:
            quiz_jobs.interrupt_active_jobs(db)  # e.g. another process judged this worker dead
        finally:
            db.close()
        return one(call_number)

    llm = fake_llm(one(1), sweep_during_second_call, one(3))
    generate(client, topic)
    assert len(llm.calls) == 2  # no third call, and the second question wasn't stored

    db_session.expire_all()
    job = db_session.query(models.QuizJob).one()
    assert job.status == "partial" and job.completed == 1 and job.error == quiz_jobs.RESTART_MESSAGE
    assert len(current_set(client, topic)["questions"]) == 1
    assert count(db_session, models.QuizQuestion) == 1
