"""Adding prerequisites without loops, and removing them."""

from app import models
from app.services import graph_service
from helpers import make_topic


def add(client, topic, prerequisite):
    """`prerequisite` must be learned before `topic`."""
    return client.post(
        "/topics/prerequisites",
        json={"topic_id": topic["id"], "prerequisite_topic_id": prerequisite["id"]},
    )


def remove(client, topic, prerequisite):
    return client.delete(f"/topics/{topic['id']}/prerequisites/{prerequisite['id']}")


def edges(client, course_id=None):
    path = "/topics/graph/json" + (f"?course_id={course_id}" if course_id else "")
    return {(e["source"], e["target"]) for e in client.get(path).json()["edges"]}


def topics(client, *names, course="Math"):
    return [make_topic(client, name, course=course) for name in names]


# --- loops are refused ----------------------------------------------------------------


def test_a_two_topic_loop_is_refused_and_nothing_is_stored(client):
    a, b = topics(client, "A", "B")
    assert add(client, b, a).status_code == 200  # A before B

    resp = add(client, a, b)  # B before A: a loop
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert "loop" in detail and "A → B → A" in detail
    assert "'B' already depends on 'A'" in detail
    assert edges(client) == {(a["id"], b["id"])}  # only the first link exists


def test_a_longer_loop_is_refused_and_the_message_shows_the_chain(client):
    a, b, c, d = topics(client, "Sets", "Functions", "Relations", "Graphs")
    for topic, prereq in [(b, a), (c, b), (d, c)]:
        assert add(client, topic, prereq).status_code == 200  # Sets -> Functions -> Relations -> Graphs

    resp = add(client, a, d)  # Graphs before Sets would close the circle
    assert resp.status_code == 400
    assert "Sets → Functions → Relations → Graphs → Sets" in resp.json()["detail"]
    assert len(edges(client)) == 3


def test_a_loop_through_the_middle_of_a_chain_is_refused(client):
    a, b, c = topics(client, "A", "B", "C")
    add(client, b, a)
    add(client, c, b)
    assert add(client, b, c).status_code == 400  # C -> B closes B -> C -> B
    assert add(client, a, c).status_code == 400  # C -> A closes A -> B -> C -> A


def test_links_that_make_no_loop_are_fine_including_diamonds_and_shortcuts(client):
    a, b, c, d = topics(client, "A", "B", "C", "D")
    # A before B and C; B and C before D (a diamond), plus the shortcut A before D.
    for topic, prereq in [(b, a), (c, a), (d, b), (d, c), (d, a)]:
        assert add(client, topic, prereq).status_code == 200
    assert len(edges(client)) == 5


def test_the_old_checks_still_apply(client):
    a, b = topics(client, "A", "B")
    other = make_topic(client, "E", course="Elsewhere")
    assert add(client, a, a).status_code == 400  # itself
    add(client, b, a)
    assert add(client, b, a).status_code == 400  # duplicate
    assert add(client, other, a).status_code == 400  # another course


def test_the_duplicate_message_wins_over_the_loop_message(client):
    a, b = topics(client, "A", "B")
    add(client, b, a)
    assert "already exists" in add(client, b, a).json()["detail"]


def test_another_users_topics_never_count_towards_a_loop(client, other_client):
    a, b = topics(client, "A", "B")
    add(client, b, a)
    # The other user builds the reverse link between their own, similarly named topics.
    x, y = topics(other_client, "A", "B")
    assert add(other_client, x, y).status_code == 200
    assert edges(other_client) == {(y["id"], x["id"])}


def test_a_loop_that_already_exists_in_old_data_does_not_break_the_graph_or_new_links(client, db_session):
    a, b, c = topics(client, "A", "B", "C")
    db_session.add_all(
        [
            models.Prerequisite(topic_id=b["id"], prerequisite_topic_id=a["id"]),
            models.Prerequisite(topic_id=a["id"], prerequisite_topic_id=b["id"]),  # a legacy loop
        ]
    )
    db_session.commit()

    assert client.get("/topics/graph/json").status_code == 200
    assert add(client, c, a).status_code == 200  # an unrelated link is still accepted
    assert add(client, a, c).status_code == 400  # but this one would loop through C
    assert [t.name for t in graph_service.get_topic_order(db_session, client.user_id)]  # ordering survives


# --- removing ------------------------------------------------------------------------------


def test_a_prerequisite_can_be_removed(client):
    a, b = topics(client, "A", "B")
    add(client, b, a)
    resp = remove(client, b, a)
    assert resp.status_code == 204 and resp.content == b""
    assert edges(client) == set()


def test_removing_one_link_leaves_the_others(client):
    a, b, c = topics(client, "A", "B", "C")
    add(client, c, a)
    add(client, c, b)
    remove(client, c, a)
    assert edges(client) == {(b["id"], c["id"])}


def test_removing_a_link_that_is_not_there_is_a_404(client):
    a, b = topics(client, "A", "B")
    resp = remove(client, b, a)
    assert resp.status_code == 404 and resp.json()["detail"] == "Prerequisite not found"
    add(client, b, a)
    assert remove(client, a, b).status_code == 404  # the other direction is a different link
    assert edges(client) == {(a["id"], b["id"])}


def test_removing_twice_is_a_404_the_second_time(client):
    a, b = topics(client, "A", "B")
    add(client, b, a)
    assert remove(client, b, a).status_code == 204
    assert remove(client, b, a).status_code == 404


def test_unknown_topics_are_a_404(client):
    a, = topics(client, "A")
    assert client.delete(f"/topics/{a['id']}/prerequisites/99999").status_code == 404
    assert client.delete(f"/topics/99999/prerequisites/{a['id']}").status_code == 404


def test_after_removing_a_link_the_reverse_link_is_allowed(client):
    a, b = topics(client, "A", "B")
    add(client, b, a)
    assert add(client, a, b).status_code == 400
    remove(client, b, a)
    assert add(client, a, b).status_code == 200  # no loop any more


def test_removing_a_link_stops_the_tutor_flagging_that_topic_as_a_gap(client, db_session):
    a, b = topics(client, "A", "B")
    add(client, b, a)
    assert [t.name for t in graph_service.get_unmastered_prerequisites(db_session, b["id"], client.user_id)] == ["A"]
    remove(client, b, a)
    db_session.expire_all()
    assert graph_service.get_unmastered_prerequisites(db_session, b["id"], client.user_id) == []


def test_removing_a_link_deletes_nothing_else(client, db_session):
    a, b = topics(client, "A", "B")
    add(client, b, a)
    remove(client, b, a)
    db_session.rollback()
    assert db_session.query(models.Topic).count() == 2
    assert db_session.query(models.Mastery).count() == 2


# --- ownership --------------------------------------------------------------------------------


def test_another_user_cannot_remove_my_link(client, other_client):
    a, b = topics(client, "A", "B")
    add(client, b, a)
    assert remove(other_client, b, a).status_code == 404
    assert edges(client) == {(a["id"], b["id"])}


def test_a_link_cannot_be_removed_through_one_topic_i_own_and_one_i_do_not(client, other_client):
    mine, = topics(client, "Mine")
    theirs, = topics(other_client, "Theirs")
    assert remove(client, mine, theirs).status_code == 404
    assert remove(client, theirs, mine).status_code == 404


def test_another_user_cannot_add_a_link_to_my_topics(client, other_client):
    a, b = topics(client, "A", "B")
    assert add(other_client, b, a).status_code == 404
    assert edges(client) == set()


def test_removing_requires_a_token(client):
    from fastapi.testclient import TestClient

    from app.main import app

    a, b = topics(client, "A", "B")
    add(client, b, a)
    assert TestClient(app).delete(f"/topics/{b['id']}/prerequisites/{a['id']}").status_code == 401
    assert edges(client) == {(a["id"], b["id"])}
