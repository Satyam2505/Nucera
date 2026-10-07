"""GET /sessions: the study-session timeline (chats, graded quizzes, self reports)."""

import pytest

from app import models
from app.services import llm_service
from helpers import make_topic


@pytest.fixture()
def llm(monkeypatch):
    monkeypatch.setattr(
        llm_service, "generate", lambda system, user, model=None, **k: llm_service.LLMResult(ok=True, text="ok")
    )


def record(client, topic_id, type_, delta=0):
    resp = client.post("/sessions", json={"topic_id": topic_id, "type": type_, "score_delta": delta})
    assert resp.status_code == 200, resp.text
    return resp.json()


def test_a_new_account_has_no_history(client):
    assert client.get("/sessions").json() == []


def test_sessions_come_back_newest_first_with_their_topic_and_type(client):
    a = make_topic(client, "Hash tables", course="DSA")["id"]
    b = make_topic(client, "Sorting", course="DSA")["id"]
    record(client, a, "self_report", 5)
    record(client, b, "quiz", -3)
    record(client, a, "chat")

    items = client.get("/sessions").json()
    assert [(i["topic_name"], i["type"], i["score_delta"]) for i in items] == [
        ("Hash tables", "chat", 0),
        ("Sorting", "quiz", -3),
        ("Hash tables", "self_report", 5),
    ]
    assert items[0]["id"] > items[1]["id"] > items[2]["id"]
    assert all(i["timestamp"] and i["topic_id"] in (a, b) for i in items)
    assert set(items[0]) == {"id", "topic_id", "topic_name", "type", "score_delta", "timestamp"}


def test_real_activity_shows_up_a_chat_question_and_a_graded_quiz(client, db_session, llm):
    topic = make_topic(client, "Hash tables", course="DSA")["id"]
    client.post(
        "/sources/text",
        json={"topic_id": topic, "source_type": "self_supplied", "title": "n", "text": "A hash table maps keys to values using a hash function."},
    )
    client.post("/ask", json={"query": "What is a hash function?", "topic_id": topic})

    quiz_set = models.QuizSet(topic_id=topic)
    quiz_set.questions.append(
        models.QuizQuestion(position=0, question_text="q?", options={"A": "a", "B": "b", "C": "c", "D": "d"}, correct_option="A")
    )
    db_session.add(quiz_set)
    db_session.commit()
    qid = quiz_set.questions[0].id
    client.post("/quiz/submit", json={"quiz_set_id": quiz_set.id, "answers": [{"question_id": qid, "selected_option": "A"}]})

    assert [(i["type"], i["score_delta"]) for i in client.get("/sessions").json()] == [("quiz", 10), ("chat", 0)]


def test_filtering_by_topic(client):
    a = make_topic(client, "A", course="DSA")["id"]
    b = make_topic(client, "B", course="DSA")["id"]
    record(client, a, "chat")
    record(client, b, "chat")
    record(client, b, "quiz", 4)
    assert {i["topic_id"] for i in client.get("/sessions", params={"topic_id": b}).json()} == {b}
    assert len(client.get("/sessions", params={"topic_id": a}).json()) == 1


def test_filtering_by_course(client):
    a = make_topic(client, "A", course="One")
    b = make_topic(client, "B", course="Two")
    record(client, a["id"], "chat")
    record(client, b["id"], "chat")
    items = client.get("/sessions", params={"course_id": a["course_id"]}).json()
    assert [i["topic_id"] for i in items] == [a["id"]]


def test_a_topic_filter_inside_a_course_filter_is_the_intersection(client):
    a = make_topic(client, "A", course="One")
    b = make_topic(client, "B", course="Two")
    record(client, a["id"], "chat")
    assert client.get("/sessions", params={"course_id": b["course_id"], "topic_id": a["id"]}).json() == []


def test_paging_with_before_id_and_limit(client):
    topic = make_topic(client, "A", course="DSA")["id"]
    ids = [record(client, topic, "chat")["id"] for _ in range(5)]  # oldest first

    page1 = client.get("/sessions", params={"limit": 2}).json()
    assert [i["id"] for i in page1] == [ids[4], ids[3]]
    page2 = client.get("/sessions", params={"limit": 2, "before_id": page1[-1]["id"]}).json()
    assert [i["id"] for i in page2] == [ids[2], ids[1]]
    page3 = client.get("/sessions", params={"limit": 2, "before_id": page2[-1]["id"]}).json()
    assert [i["id"] for i in page3] == [ids[0]]
    assert client.get("/sessions", params={"limit": 2, "before_id": ids[0]}).json() == []


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 201}, {"before_id": 0}])
def test_bad_paging_parameters_are_rejected(client, params):
    assert client.get("/sessions", params=params).status_code == 422


def test_other_users_sessions_are_never_included(client, other_client):
    mine = make_topic(client, "Mine", course="DSA")["id"]
    theirs = make_topic(other_client, "Theirs", course="DSA")["id"]
    record(client, mine, "chat")
    record(other_client, theirs, "quiz", 8)
    assert [i["topic_name"] for i in client.get("/sessions").json()] == ["Mine"]
    assert [i["topic_name"] for i in other_client.get("/sessions").json()] == ["Theirs"]


def test_another_users_topic_or_course_filter_is_a_404_not_an_empty_list(client, other_client):
    theirs = make_topic(other_client, "Theirs", course="DSA")
    record(other_client, theirs["id"], "chat")
    assert client.get("/sessions", params={"topic_id": theirs["id"]}).status_code == 404
    assert client.get("/sessions", params={"course_id": theirs["course_id"]}).status_code == 404


def test_deleting_a_topic_removes_its_sessions_from_the_history(client):
    a = make_topic(client, "A", course="DSA")["id"]
    b = make_topic(client, "B", course="DSA")["id"]
    record(client, a, "chat")
    record(client, b, "chat")
    client.delete(f"/topics/{a}")
    assert [i["topic_id"] for i in client.get("/sessions").json()] == [b]


def test_the_history_requires_a_token():
    from fastapi.testclient import TestClient

    from app.main import app

    assert TestClient(app).get("/sessions").status_code == 401
