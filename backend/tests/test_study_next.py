"""GET /courses/{id}/next: what to study next, from the prerequisite graph and mastery."""

from datetime import datetime, timedelta

import pytest

from app import models
from helpers import make_course, make_module, make_topic


def link(client, topic, prerequisite):
    """`prerequisite` must be learned before `topic`."""
    r = client.post("/topics/prerequisites", json={"topic_id": topic["id"], "prerequisite_topic_id": prerequisite["id"]})
    assert r.status_code == 200, r.text


def master(client, topic, score=90):
    assert client.put(f"/mastery/{topic['id']}", json={"score": score}).status_code == 200


def fade(db, topic, estimate, stability, age_days, stored_score=None):
    """The topic was reviewed `age_days` ago with this estimate and half-life."""
    m = db.get(models.Mastery, topic["id"])
    m.estimate, m.stability_days = estimate, stability
    m.last_reviewed_at = datetime.utcnow() - timedelta(days=age_days)
    m.score = stored_score if stored_score is not None else round(estimate * 100)
    m.status = models.MasteryStatus.mastered if m.score >= 80 else models.MasteryStatus.in_progress
    db.commit()


def nxt(client, course_id, **params):
    resp = client.get(f"/courses/{course_id}/next", params=params)
    assert resp.status_code == 200, resp.text
    return resp.json()


def names(steps):
    return [s["topic_name"] for s in steps]


@pytest.fixture()
def chain(client):
    """Sets -> Functions -> Relations (each is the prerequisite of the next)."""
    a = make_topic(client, "Sets", course="Math")
    b = make_topic(client, "Functions", course="Math")
    c = make_topic(client, "Relations", course="Math")
    link(client, b, a)
    link(client, c, b)
    return a, b, c


# --- ready topics -----------------------------------------------------------------------------------


def test_in_a_fresh_chain_only_the_first_topic_is_ready_and_it_says_what_it_unlocks(client, chain):
    a, _b, _c = chain
    steps = nxt(client, a["course_id"])
    assert names(steps) == ["Sets"]
    assert steps[0]["kind"] == "ready" and steps[0]["reason"] == "Unlocks 2 topics"
    assert steps[0]["score"] == 0 and steps[0]["status"] == "unmastered" and steps[0]["due_for_review"] is False


def test_mastering_a_prerequisite_makes_the_next_topic_ready(client, chain):
    a, b, c = chain
    master(client, a)
    steps = nxt(client, a["course_id"])
    assert names(steps) == ["Functions"]  # Relations still waits on Functions
    assert steps[0]["reason"] == "Unlocks 1 topic"
    master(client, b)
    assert names(nxt(client, a["course_id"])) == ["Relations"]
    assert nxt(client, a["course_id"])[0]["reason"] == "Next in the course"  # unlocks nothing


def test_a_topic_in_progress_is_ready_and_its_score_is_in_the_reason(client, chain):
    a, _b, _c = chain
    master(client, a, 55)  # not mastered: still the thing to work on
    step = nxt(client, a["course_id"])[0]
    assert step["topic_name"] == "Sets" and step["reason"] == "Unlocks 2 topics. In progress (55%)"


def test_topics_with_no_prerequisites_rank_by_how_much_they_unlock_then_course_order(client):
    make_topic(client, "Lone", course="C")
    root = make_topic(client, "Root", course="C")
    leaf1 = make_topic(client, "Leaf1", course="C")
    leaf2 = make_topic(client, "Leaf2", course="C")
    link(client, leaf1, root)
    link(client, leaf2, root)
    make_topic(client, "Other", course="C")
    steps = nxt(client, root["course_id"], limit=10)
    # Root unlocks 2; Lone and Other unlock nothing and keep course order.
    assert names(steps) == ["Root", "Lone", "Other"]


def test_a_topic_marked_missed_or_flagged_comes_first_among_the_ready(client):
    a = make_topic(client, "Alpha", course="C")
    b = make_topic(client, "Beta", course="C")
    c = make_topic(client, "Gamma", course="C")
    client.post(f"/mastery/{c['id']}/missed")
    client.post(f"/mastery/{b['id']}/toggle-revision")
    steps = nxt(client, a["course_id"], limit=10)
    # Missed and flagged share the same priority (ahead of Alpha); course order breaks the tie.
    assert names(steps) == ["Beta", "Gamma", "Alpha"]
    assert steps[0]["reason"] == "Flagged for revision" and steps[1]["reason"] == "Marked as missed"


def test_the_default_is_three_and_the_limit_is_validated(client):
    first = make_topic(client, "T0", course="C")
    for n in range(1, 6):
        make_topic(client, f"T{n}", course="C")
    assert len(nxt(client, first["course_id"])) == 3
    assert len(nxt(client, first["course_id"], limit=5)) == 5
    for bad in (0, 11, -1):
        assert client.get(f"/courses/{first['course_id']}/next", params={"limit": bad}).status_code == 422


# --- reviews first -------------------------------------------------------------------------------------------


def test_a_faded_topic_is_a_review_and_comes_before_anything_new(client, db_session, chain):
    a, b, _c = chain
    master(client, a)  # then it fades: reviewed 3 days ago with a 3-day half-life
    fade(db_session, a, estimate=0.9, stability=3.0, age_days=3)
    steps = nxt(client, a["course_id"], limit=10)
    assert names(steps)[0] == "Sets" and steps[0]["kind"] == "review"
    assert steps[0]["due_for_review"] is True
    assert steps[0]["reason"].startswith("Due for review: 2 days overdue")  # due after 0.97 days; now 3
    assert steps[0]["score"] == 45 and steps[0]["status"] == "in_progress"  # 90 x 0.5, no longer mastered


def test_a_faded_prerequisite_no_longer_unlocks_what_depends_on_it(client, db_session, chain):
    a, b, _c = chain
    master(client, a)
    assert names(nxt(client, a["course_id"])) == ["Functions"]
    fade(db_session, a, estimate=0.9, stability=3.0, age_days=3)  # now shows 45: not mastered
    assert names(nxt(client, a["course_id"], limit=10)) == ["Sets"]  # Sets again; Functions waits


def test_the_most_overdue_review_comes_first(client, db_session):
    a = make_topic(client, "Recent", course="C")
    b = make_topic(client, "Ancient", course="C")
    fade(db_session, a, 0.9, 3.0, age_days=2)
    fade(db_session, b, 0.9, 3.0, age_days=9)
    steps = nxt(client, a["course_id"], limit=10)
    assert names(steps) == ["Ancient", "Recent"] and all(s["kind"] == "review" for s in steps)
    assert steps[0]["reason"] == "Due for review: 8 days overdue" and steps[1]["reason"] == "Due for review: 1 day overdue"


def test_a_topic_just_starting_to_fade_says_so_without_counting_days(client, db_session):
    a = make_topic(client, "Fresh", course="C")
    fade(db_session, a, 0.9, 3.0, age_days=1.2)  # due after 0.97 days: 0.2 overdue
    assert nxt(client, a["course_id"])[0]["reason"] == "Due for review: it has started to fade"


def test_a_topic_still_fresh_is_not_a_review(client, db_session):
    a = make_topic(client, "Solid", course="C")
    fade(db_session, a, 0.9, 3.0, age_days=0.5)
    assert nxt(client, a["course_id"]) == []  # mastered and not yet fading


def test_a_topic_never_learned_is_never_a_review(client, db_session):
    a = make_topic(client, "Blank", course="C")
    assert nxt(client, a["course_id"])[0]["kind"] == "ready"


# --- nothing to do, odd data, and who can ask ------------------------------------------------------------------


def test_when_everything_is_mastered_and_fresh_there_is_nothing_to_suggest(client, chain):
    a, b, c = chain
    for t in (a, b, c):
        master(client, t)
    assert nxt(client, a["course_id"]) == []


def test_an_empty_course_has_nothing_to_suggest(client):
    course = make_course(client, "Empty")
    make_module(client, course["id"], "M")
    assert nxt(client, course["id"]) == []


def test_a_mastered_row_written_without_the_model_is_never_due(client, db_session, chain):
    a, _b, _c = chain
    m = db_session.get(models.Mastery, a["id"])
    m.score, m.status = 95, models.MasteryStatus.mastered  # as old code would have left it
    db_session.commit()
    assert names(nxt(client, a["course_id"])) == ["Functions"]


def test_a_loop_already_in_old_data_still_gets_a_suggestion(client, db_session):
    a = make_topic(client, "A", course="C")
    b = make_topic(client, "B", course="C")
    db_session.add_all(
        [
            models.Prerequisite(topic_id=a["id"], prerequisite_topic_id=b["id"]),
            models.Prerequisite(topic_id=b["id"], prerequisite_topic_id=a["id"]),
        ]
    )
    db_session.commit()
    steps = nxt(client, a["course_id"])
    assert names(steps) == ["A", "B"] and all(s["reason"] == "Next in the course" for s in steps)


def test_it_only_looks_at_the_one_course(client):
    here = make_topic(client, "Here", course="One")
    make_topic(client, "There", course="Two")
    assert names(nxt(client, here["course_id"])) == ["Here"]


def test_the_suggestion_includes_the_module_for_context(client):
    t = make_topic(client, "Topic", course="C", module="Chapter 3")
    assert nxt(client, t["course_id"])[0]["module_name"] == "Chapter 3"


def test_another_users_course_is_a_404_and_my_suggestions_never_include_theirs(client, other_client):
    mine = make_topic(client, "Mine", course="C")
    theirs = make_topic(other_client, "Theirs", course="C")
    assert other_client.get(f"/courses/{mine['course_id']}/next").status_code == 404
    assert names(nxt(client, mine["course_id"])) == ["Mine"]
    assert names(nxt(other_client, theirs["course_id"])) == ["Theirs"]


def test_it_requires_a_token():
    from fastapi.testclient import TestClient

    from app.main import app

    assert TestClient(app).get("/courses/1/next").status_code == 401
