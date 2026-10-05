"""The mastery status rule (services/mastery_service) and the endpoints that use it."""

import pytest

from app import models
from app.models import MasteryStatus as S
from app.services.mastery_service import apply_score_delta, set_score, status_for_score
from helpers import make_topic


def _mastery(score=0, status=S.unmastered):
    return models.Mastery(topic_id=1, score=score, status=status)


# --- the rule ---------------------------------------------------------------


@pytest.mark.parametrize(
    "score,expected",
    [(0, S.unmastered), (1, S.in_progress), (79, S.in_progress), (80, S.mastered), (100, S.mastered)],
)
def test_status_for_score_boundaries(score, expected):
    assert status_for_score(score) == expected


# (start score, start status, delta) -> (score, status)
DELTA_CASES = [
    pytest.param(0, S.unmastered, 10, 10, S.in_progress, id="first-progress"),
    pytest.param(75, S.in_progress, 5, 80, S.mastered, id="reaches-mastered-at-80"),
    pytest.param(79, S.in_progress, 1, 80, S.mastered, id="79-to-80"),
    pytest.param(80, S.mastered, -1, 79, S.in_progress, id="falls-out-of-mastered"),
    pytest.param(30, S.in_progress, -10, 20, S.in_progress, id="stays-in-progress"),
    pytest.param(5, S.in_progress, -10, 0, S.unmastered, id="clamps-at-0-and-resets-status"),
    pytest.param(0, S.unmastered, -10, 0, S.unmastered, id="already-at-0"),
    pytest.param(95, S.mastered, 10, 100, S.mastered, id="clamps-at-100"),
    pytest.param(100, S.mastered, 10, 100, S.mastered, id="already-at-100"),
    pytest.param(40, S.in_progress, 0, 40, S.in_progress, id="zero-delta"),
    pytest.param(90, S.mastered, -90, 0, S.unmastered, id="mastered-straight-to-0"),
    # A stale status is corrected by any change, so score and status can't drift.
    pytest.param(85, S.in_progress, 0, 85, S.mastered, id="stale-status-corrected"),
]


@pytest.mark.parametrize("score,status,delta,new_score,new_status", DELTA_CASES)
def test_apply_score_delta_transitions(score, status, delta, new_score, new_status):
    mastery = _mastery(score, status)
    apply_score_delta(mastery, delta)
    assert (mastery.score, mastery.status) == (new_score, new_status)


# --- "missed" ---------------------------------------------------------------

MISSED_CASES = [
    pytest.param(30, 5, 35, S.in_progress, id="positive-delta-clears-missed"),
    pytest.param(0, 10, 10, S.in_progress, id="positive-from-zero-clears-missed"),
    pytest.param(75, 10, 85, S.mastered, id="positive-delta-can-clear-straight-to-mastered"),
    pytest.param(30, -5, 25, S.missed, id="negative-delta-keeps-missed"),
    pytest.param(30, 0, 30, S.missed, id="zero-delta-keeps-missed"),
    pytest.param(0, -5, 0, S.missed, id="missed-at-zero-stays-missed"),
    pytest.param(100, 5, 100, S.missed, id="no-actual-increase-at-the-cap-keeps-missed"),
]


@pytest.mark.parametrize("score,delta,new_score,new_status", MISSED_CASES)
def test_missed_is_cleared_only_by_a_real_increase(score, delta, new_score, new_status):
    mastery = _mastery(score, S.missed)
    apply_score_delta(mastery, delta)
    assert (mastery.score, mastery.status) == (new_score, new_status)


def test_set_score_follows_the_same_rule():
    for score, expected in [(85, S.mastered), (50, S.in_progress), (0, S.unmastered)]:
        mastery = _mastery(40, S.in_progress)
        set_score(mastery, score)
        assert (mastery.score, mastery.status) == (score, expected)

    mastery = _mastery(40, S.in_progress)
    set_score(mastery, 150)
    assert (mastery.score, mastery.status) == (100, S.mastered)
    set_score(mastery, -20)
    assert (mastery.score, mastery.status) == (0, S.unmastered)


def test_set_score_and_missed():
    lower = _mastery(50, S.missed)
    set_score(lower, 20)
    assert (lower.score, lower.status) == (20, S.missed)

    same = _mastery(50, S.missed)
    set_score(same, 50)
    assert same.status == S.missed

    higher = _mastery(50, S.missed)
    set_score(higher, 51)
    assert (higher.score, higher.status) == (51, S.in_progress)


# --- endpoints --------------------------------------------------------------


def _get(client, topic_id):
    return client.get(f"/mastery/{topic_id}").json()


def test_put_mastery_derives_the_status_from_the_score(client):
    topic = make_topic(client, "T")["id"]

    for score, status in [(85, "mastered"), (50, "in_progress"), (0, "unmastered")]:
        resp = client.put(f"/mastery/{topic}", json={"score": score})
        assert resp.status_code == 200, resp.text
        assert (resp.json()["score"], resp.json()["status"]) == (score, status)

    assert client.put(f"/mastery/{topic}", json={"score": 150}).json()["score"] == 100
    assert client.put(f"/mastery/{topic}", json={"score": -5}).json()["score"] == 0


def test_put_mastery_rejects_a_status_and_changes_nothing(client):
    topic = make_topic(client, "T")["id"]
    client.put(f"/mastery/{topic}", json={"score": 50})

    resp = client.put(f"/mastery/{topic}", json={"score": 90, "status": "unmastered"})
    assert resp.status_code == 422
    assert client.put(f"/mastery/{topic}", json={"status": "mastered"}).status_code == 422
    after = _get(client, topic)
    assert (after["score"], after["status"]) == (50, "in_progress")


def test_put_mastery_with_an_empty_body_is_a_no_op(client):
    topic = make_topic(client, "T")["id"]
    client.put(f"/mastery/{topic}", json={"score": 50})
    resp = client.put(f"/mastery/{topic}", json={})
    assert resp.status_code == 200
    assert (resp.json()["score"], resp.json()["status"]) == (50, "in_progress")


def test_missed_endpoint_marks_missed_and_keeps_the_score(client):
    topic = make_topic(client, "T")["id"]
    client.put(f"/mastery/{topic}", json={"score": 60})

    resp = client.post(f"/mastery/{topic}/missed")
    assert resp.status_code == 200
    assert (resp.json()["score"], resp.json()["status"]) == (60, "missed")

    # Not raised -> still missed; raised -> cleared into the derived status.
    assert client.put(f"/mastery/{topic}", json={"score": 40}).json()["status"] == "missed"
    assert client.put(f"/mastery/{topic}", json={"score": 40}).json()["status"] == "missed"
    cleared = client.put(f"/mastery/{topic}", json={"score": 41}).json()
    assert (cleared["score"], cleared["status"]) == (41, "in_progress")


def test_a_positive_session_clears_missed_and_a_negative_one_does_not(client):
    topic = make_topic(client, "T")["id"]
    client.put(f"/mastery/{topic}", json={"score": 30})
    client.post(f"/mastery/{topic}/missed")

    def session(delta):
        resp = client.post(
            "/sessions", json={"topic_id": topic, "type": "self_report", "score_delta": delta}
        )
        assert resp.status_code == 200, resp.text

    session(-10)
    assert (_get(client, topic)["score"], _get(client, topic)["status"]) == (20, "missed")
    session(10)
    assert (_get(client, topic)["score"], _get(client, topic)["status"]) == (30, "in_progress")
    session(50)
    assert (_get(client, topic)["score"], _get(client, topic)["status"]) == (80, "mastered")
    session(-1)
    assert _get(client, topic)["status"] == "in_progress"


def test_toggle_revision_flips_the_flag_without_touching_score_or_status(client):
    topic = make_topic(client, "T")["id"]
    client.put(f"/mastery/{topic}", json={"score": 55})
    client.post(f"/mastery/{topic}/missed")

    first = client.post(f"/mastery/{topic}/toggle-revision").json()
    assert first["flagged_for_revision"] is True
    assert (first["score"], first["status"]) == (55, "missed")

    second = client.post(f"/mastery/{topic}/toggle-revision").json()
    assert second["flagged_for_revision"] is False
    assert (second["score"], second["status"]) == (55, "missed")


def test_mastery_is_created_with_the_topic_and_starts_unmastered(client):
    topic = make_topic(client, "T")["id"]
    mastery = _get(client, topic)
    assert (mastery["score"], mastery["status"], mastery["flagged_for_revision"]) == (
        0,
        "unmastered",
        False,
    )
