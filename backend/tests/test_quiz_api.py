"""Quiz endpoints: reading, generating, grading, regeneration history, errors.

The model is mocked (as in the tutor tests) and chunks are inserted directly,
so none of this needs Ollama or the embedding model.
"""

import json

import pytest
from sqlalchemy import func

from app import models
from app.services import llm_service, quiz_service
from helpers import make_topic


def make_q(n):
    return {
        "question": f"What does statement number {n} describe?",
        "options": {"A": f"Alpha {n}", "B": f"Bravo {n}", "C": f"Charlie {n}", "D": f"Delta {n}"},
        "answer": "A",
        "explanation": f"Explanation of fact {n}.",
        "sources": [1] if n % 2 else [1, 2],
    }


def good_reply(count=5):
    return json.dumps({"questions": [make_q(n) for n in range(1, count + 1)]})


class FakeLLM:
    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls = []

    def __call__(self, system_prompt, user_prompt, model=None, **kwargs):
        self.calls.append({"system": system_prompt, "user": user_prompt, **kwargs})
        reply = self.replies.pop(0) if len(self.replies) > 1 else self.replies[0]
        if isinstance(reply, llm_service.LLMResult):
            return reply
        return llm_service.LLMResult(ok=True, text=reply)


@pytest.fixture()
def fake_llm(monkeypatch):
    def install(*replies):
        fake = FakeLLM(*replies)
        monkeypatch.setattr(llm_service, "generate", fake)
        return fake

    return install


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


# --- reading (never generates) ---------------------------------------------------------


def test_get_without_a_set_returns_null_and_never_calls_the_model(client, topic, fake_llm):
    llm = fake_llm(good_reply())
    resp = client.get(f"/quiz/{topic}")
    assert resp.status_code == 200
    assert resp.json() == {"quiz_set": None, "has_material": True}
    assert llm.calls == []


def test_get_reports_when_there_is_no_material(client, fake_llm):
    llm = fake_llm(good_reply())
    empty_topic = make_topic(client, "Empty", course="DSA")["id"]
    assert client.get(f"/quiz/{empty_topic}").json() == {"quiz_set": None, "has_material": False}
    assert llm.calls == []


def test_get_never_creates_a_set_however_often_it_is_called(client, db_session, topic, fake_llm):
    llm = fake_llm(good_reply())
    for _ in range(3):
        client.get(f"/quiz/{topic}")
    assert llm.calls == []
    assert count(db_session, models.QuizSet) == 0


# --- generating ----------------------------------------------------------------------------


def test_generate_creates_a_set_of_grounded_questions_without_the_answers(client, db_session, topic, fake_llm):
    llm = fake_llm(good_reply(5))
    resp = generate(client, topic)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body["questions"]) == 5
    assert body["attempt"] is None
    for position, question in enumerate(body["questions"]):
        assert question["position"] == position
        assert sorted(question["options"]) == ["A", "B", "C", "D"]
        assert set(question) == {"id", "position", "question_text", "options"}
    # Neither the keys nor the explanations leave the server before grading.
    assert "correct_option" not in resp.text
    assert "Explanation of fact" not in resp.text

    call = llm.calls[0]
    assert call["json_mode"] is True
    assert "Notes A, p. 3" in call["user"] and "Notes B" in call["user"]
    assert count(db_session, models.QuizSet) == 1


def test_generated_questions_keep_citations_built_from_the_excerpts(client, db_session, topic, fake_llm):
    fake_llm(good_reply(5))
    quiz_set_id = generate(client, topic).json()["id"]
    db_session.rollback()
    questions = (
        db_session.query(models.QuizQuestion)
        .filter(models.QuizQuestion.quiz_set_id == quiz_set_id)
        .order_by(models.QuizQuestion.position)
        .all()
    )
    assert questions[0].sources == [{"source": "Notes A", "page": 3}]
    assert questions[1].sources == [{"source": "Notes A", "page": 3}, {"source": "Notes B", "page": None}]
    assert all(q.explanation for q in questions)


def test_get_returns_the_latest_set_after_generation(client, topic, fake_llm):
    fake_llm(good_reply())
    created = generate(client, topic).json()
    state = client.get(f"/quiz/{topic}").json()
    assert state["has_material"] is True
    assert state["quiz_set"]["id"] == created["id"]
    assert [q["id"] for q in state["quiz_set"]["questions"]] == [q["id"] for q in created["questions"]]
    assert state["quiz_set"]["attempt"] is None


def test_count_controls_the_number_of_questions_and_is_validated(client, topic, fake_llm):
    llm = fake_llm(good_reply(10))
    assert len(generate(client, topic, count=3).json()["questions"]) == 3
    assert "Write 3 multiple-choice questions" in llm.calls[0]["user"]
    assert len(generate(client, topic, count=10).json()["questions"]) == 10
    assert generate(client, topic, count=2).status_code == 422
    assert generate(client, topic, count=11).status_code == 422
    assert len(generate(client, topic).json()["questions"]) == 5  # the default


def test_no_material_is_a_409_and_the_model_is_never_called(client, db_session, fake_llm):
    llm = fake_llm(good_reply())
    empty_topic = make_topic(client, "Empty", course="DSA")["id"]
    resp = generate(client, empty_topic)
    assert resp.status_code == 409
    assert "Add study material first" in resp.json()["detail"]
    assert llm.calls == []
    assert count(db_session, models.QuizSet) == 0


def test_malformed_json_then_a_good_retry_succeeds(client, topic, fake_llm):
    llm = fake_llm("{this is not json", good_reply(4))
    resp = generate(client, topic)
    assert resp.status_code == 200
    assert len(resp.json()["questions"]) == 4
    assert len(llm.calls) == 2


def test_partially_invalid_output_keeps_only_the_valid_questions(client, topic, fake_llm):
    items = [make_q(1), {**make_q(2), "answer": "Z"}, make_q(3), {**make_q(4), "sources": [9]}, make_q(5)]
    fake_llm(json.dumps({"questions": items}))
    resp = generate(client, topic)
    assert resp.status_code == 200
    assert [q["question_text"] for q in resp.json()["questions"]] == [
        make_q(1)["question"],
        make_q(3)["question"],
        make_q(5)["question"],
    ]


def test_all_invalid_output_is_a_503_and_nothing_is_stored(client, db_session, topic, fake_llm):
    llm = fake_llm("garbage", json.dumps({"questions": [{**make_q(1), "answer": "Z"}]}))
    resp = generate(client, topic)
    assert resp.status_code == 503
    assert "usable questions" in resp.json()["detail"]
    assert len(llm.calls) == 2  # exactly one retry
    assert count(db_session, models.QuizSet) == 0
    assert count(db_session, models.QuizQuestion) == 0


def test_too_few_valid_questions_is_a_503(client, db_session, topic, fake_llm):
    fake_llm(json.dumps({"questions": [make_q(1), make_q(2)]}))  # 2 valid, both tries
    assert generate(client, topic).status_code == 503
    assert count(db_session, models.QuizSet) == 0


def test_ollama_down_is_a_503_with_a_clear_message_and_no_retry(client, db_session, topic, fake_llm):
    llm = fake_llm(llm_service.LLMResult(ok=False, error="Ollama is not running or unreachable."))
    resp = generate(client, topic)
    assert resp.status_code == 503
    assert "Ollama is not running" in resp.json()["detail"]
    assert len(llm.calls) == 1
    assert count(db_session, models.QuizSet) == 0


def test_a_second_generation_for_the_same_topic_in_flight_is_a_409(client, topic, fake_llm):
    llm = fake_llm(good_reply())
    with quiz_service.generation_slot(topic):
        resp = generate(client, topic)
    assert resp.status_code == 409
    assert "already in progress" in resp.json()["detail"]
    assert llm.calls == []
    assert generate(client, topic).status_code == 200  # the slot was released


def test_the_slot_is_released_after_a_failed_generation(client, topic, fake_llm):
    fake_llm(llm_service.LLMResult(ok=False, error="down"), good_reply())
    assert generate(client, topic).status_code == 503
    assert generate(client, topic).status_code == 200


# --- grading ---------------------------------------------------------------------------------------


@pytest.fixture()
def quiz(client, db_session, topic, fake_llm):
    fake_llm(good_reply(5))
    created = generate(client, topic).json()
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
    assert ok["sources"] == [{"source": "Notes A", "page": 3}]
    assert bad["is_correct"] is False and bad["chosen"] == wrong_option(quiz["keys"][second])
    assert bad["correct_option"] == quiz["keys"][second]
    assert bad["sources"] == [{"source": "Notes A", "page": 3}, {"source": "Notes B", "page": None}]
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


# --- regeneration keeps history --------------------------------------------------------------------


def test_regenerating_adds_a_new_set_and_keeps_old_sets_and_attempts(client, db_session, topic, fake_llm, quiz):
    submit(client, quiz, answers(quiz["keys"], correct_ids=quiz["ids"]))
    old_questions = count(db_session, models.QuizQuestion)

    fake_llm(good_reply(5))
    new = generate(client, topic).json()
    assert new["id"] != quiz["set"]
    assert new["attempt"] is None

    assert count(db_session, models.QuizSet) == 2
    assert count(db_session, models.QuizAttempt) == 1  # the earlier attempt survives
    assert count(db_session, models.QuizQuestion) == old_questions + 5
    latest = client.get(f"/quiz/{topic}").json()["quiz_set"]
    assert latest["id"] == new["id"] and latest["attempt"] is None

    # The new set can be graded in its own right.
    new_keys = keys_for(db_session, new["id"])
    graded = client.post(
        "/quiz/submit",
        json={"quiz_set_id": new["id"], "answers": answers(new_keys, correct_ids=list(new_keys))},
    )
    assert graded.status_code == 200
    assert count(db_session, models.QuizAttempt) == 2


# --- cross-user ----------------------------------------------------------------------------------------


def test_other_users_cannot_read_generate_or_grade_my_quiz(client, other_client, quiz, fake_llm):
    llm = fake_llm(good_reply())
    assert other_client.get(f"/quiz/{quiz['topic']}").status_code == 404
    assert other_client.post(f"/quiz/{quiz['topic']}/generate").status_code == 404
    resp = other_client.post(
        "/quiz/submit",
        json={"quiz_set_id": quiz["set"], "answers": answers(quiz["keys"], correct_ids=quiz["ids"])},
    )
    assert resp.status_code == 404
    assert llm.calls == []


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
    fake_llm(good_reply(5))
    other_set = generate(client, topic).json()
    resp = client.post(
        "/quiz/submit",
        json={
            "quiz_set_id": other_set["id"],
            "answers": answers(quiz["keys"], correct_ids=quiz["ids"][:1]),
        },
    )
    assert resp.status_code == 400
    assert count(db_session, models.QuizAttempt) == 0
