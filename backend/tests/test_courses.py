"""Course -> Module -> Topic API: CRUD, ordering, cascades, ownership, tree."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, func

from app import models
from app.database import engine
from helpers import make_course, make_module, make_topic


def _tree(client, course_id):
    resp = client.get(f"/courses/{course_id}/tree")
    assert resp.status_code == 200, resp.text
    return resp.json()


def _module_names(tree):
    return [m["name"] for m in tree["modules"]]


def _topic_names(module):
    return [t["name"] for t in module["topics"]]


def _count(db_session, model):
    db_session.rollback()  # drop any stale snapshot; the API used its own session
    return db_session.query(func.count()).select_from(model).scalar()


# --- Courses -----------------------------------------------------------------


def test_create_list_update_delete_course(client):
    created = client.post("/courses", json={"name": "  Biology  ", "description": "Cells"})
    assert created.status_code == 200, created.text
    course = created.json()
    assert course["name"] == "Biology"  # trimmed
    assert (course["module_count"], course["topic_count"], course["avg_score"]) == (0, 0, 0)

    assert [c["id"] for c in client.get("/courses").json()] == [course["id"]]

    renamed = client.patch(f"/courses/{course['id']}", json={"name": "Bio 101"})
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "Bio 101"
    assert renamed.json()["description"] == "Cells"  # untouched when not sent

    cleared = client.patch(f"/courses/{course['id']}", json={"description": None})
    assert cleared.json()["description"] is None

    assert client.delete(f"/courses/{course['id']}").status_code == 204
    assert client.get("/courses").json() == []
    assert client.get(f"/courses/{course['id']}/tree").status_code == 404


def test_course_names_must_be_non_empty_and_unique_per_user(client, other_client):
    assert client.post("/courses", json={"name": "   "}).status_code == 422

    assert client.post("/courses", json={"name": "Algebra"}).status_code == 200
    assert client.post("/courses", json={"name": "Algebra"}).status_code == 400

    second = client.post("/courses", json={"name": "Geometry"}).json()
    assert client.patch(f"/courses/{second['id']}", json={"name": "Algebra"}).status_code == 400
    # Renaming a course to its own current name is not a conflict.
    assert client.patch(f"/courses/{second['id']}", json={"name": "Geometry"}).status_code == 200

    # The same name under a different account is fine.
    assert other_client.post("/courses", json={"name": "Algebra"}).status_code == 200


def test_course_list_reports_module_topic_counts_and_average_mastery(client):
    topic_a = make_topic(client, "A", course="Math", module="One")
    topic_b = make_topic(client, "B", course="Math", module="Two")
    make_topic(client, "C", course="Math", module="Two")
    client.put(f"/mastery/{topic_a['id']}", json={"score": 90})
    client.put(f"/mastery/{topic_b['id']}", json={"score": 30})

    (course,) = client.get("/courses").json()
    assert course["module_count"] == 2
    assert course["topic_count"] == 3
    assert course["avg_score"] == 40  # (90 + 30 + 0) / 3


# --- Tree --------------------------------------------------------------------


def test_tree_returns_modules_and_topics_in_order_with_mastery(client):
    course = make_course(client, "Math")
    one = make_module(client, course["id"], "One")
    two = make_module(client, course["id"], "Two")
    first = client.post(
        "/topics", json={"name": "First", "module_id": one["id"], "description": "d"}
    ).json()
    client.post("/topics", json={"name": "Second", "module_id": one["id"]})
    client.post("/topics", json={"name": "Third", "module_id": two["id"]})
    client.put(f"/mastery/{first['id']}", json={"score": 85})
    client.post(f"/mastery/{first['id']}/toggle-revision")

    tree = _tree(client, course["id"])
    assert tree["name"] == "Math"
    assert _module_names(tree) == ["One", "Two"]
    assert [m["position"] for m in tree["modules"]] == [0, 1]
    assert _topic_names(tree["modules"][0]) == ["First", "Second"]
    assert _topic_names(tree["modules"][1]) == ["Third"]

    first_node = tree["modules"][0]["topics"][0]
    assert first_node["description"] == "d"
    assert first_node["score"] == 85
    assert first_node["status"] == "mastered"
    assert first_node["flagged_for_revision"] is True
    second_node = tree["modules"][0]["topics"][1]
    assert (second_node["score"], second_node["status"]) == (0, "unmastered")
    assert second_node["flagged_for_revision"] is False


def test_tree_query_count_does_not_grow_with_the_number_of_topics(client):
    small = make_course(client, "Small")
    make_topic(client, "Only", course="Small", module="M")
    big = make_course(client, "Big")
    for module_index in range(3):
        for topic_index in range(4):
            make_topic(client, f"T{module_index}-{topic_index}", course="Big", module=f"M{module_index}")

    statements = []

    def record(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", record)
    try:
        _tree(client, small["id"])
        small_count = len(statements)
        statements.clear()
        _tree(client, big["id"])
        big_count = len(statements)
    finally:
        event.remove(engine, "before_cursor_execute", record)

    assert big_count == small_count


# --- Modules -----------------------------------------------------------------


def test_modules_are_appended_in_order_and_can_be_reordered(client):
    course = make_course(client, "Math")
    ids = [make_module(client, course["id"], name)["id"] for name in ("A", "B", "C")]
    assert _module_names(_tree(client, course["id"])) == ["A", "B", "C"]

    resp = client.put(f"/courses/{course['id']}/modules/order", json={"ids": [ids[2], ids[0], ids[1]]})
    assert resp.status_code == 200, resp.text
    tree = resp.json()
    assert _module_names(tree) == ["C", "A", "B"]
    assert [m["position"] for m in tree["modules"]] == [0, 1, 2]


@pytest.mark.parametrize(
    "build_ids",
    [
        lambda ids: ids[:-1],  # missing one
        lambda ids: ids + [999999],  # unknown extra
        lambda ids: [ids[0], ids[0], ids[1]],  # duplicate
        lambda ids: [],
    ],
)
def test_reorder_rejects_anything_but_the_exact_set_of_ids(client, build_ids):
    course = make_course(client, "Math")
    ids = [make_module(client, course["id"], name)["id"] for name in ("A", "B", "C")]

    resp = client.put(f"/courses/{course['id']}/modules/order", json={"ids": build_ids(ids)})
    assert resp.status_code == 400
    assert _module_names(_tree(client, course["id"])) == ["A", "B", "C"]  # unchanged


def test_patch_module_renames_and_moves_to_a_position(client):
    course = make_course(client, "Math")
    ids = [make_module(client, course["id"], name)["id"] for name in ("A", "B", "C")]

    resp = client.patch(f"/modules/{ids[2]}", json={"name": "C2", "description": "x", "position": 0})
    assert resp.status_code == 200, resp.text
    tree = resp.json()
    assert _module_names(tree) == ["C2", "A", "B"]
    assert tree["modules"][0]["description"] == "x"
    assert [m["position"] for m in tree["modules"]] == [0, 1, 2]

    # A position past the end clamps to the last slot.
    tree = client.patch(f"/modules/{ids[2]}", json={"position": 50}).json()
    assert _module_names(tree) == ["A", "B", "C2"]


def test_deleting_a_module_keeps_remaining_positions_contiguous(client):
    course = make_course(client, "Math")
    ids = [make_module(client, course["id"], name)["id"] for name in ("A", "B", "C")]

    assert client.delete(f"/modules/{ids[0]}").status_code == 204

    tree = _tree(client, course["id"])
    assert _module_names(tree) == ["B", "C"]
    assert [m["position"] for m in tree["modules"]] == [0, 1]
    # The next module lands after them, not on top of one.
    new = make_module(client, course["id"], "D")
    assert new["position"] == 2


# --- Topics ------------------------------------------------------------------


def test_topics_are_appended_reordered_and_repacked_after_delete(client):
    course = make_course(client, "Math")
    module = make_module(client, course["id"], "One")
    ids = [
        client.post("/topics", json={"name": n, "module_id": module["id"]}).json()["id"]
        for n in ("A", "B", "C")
    ]

    resp = client.put(f"/modules/{module['id']}/topics/order", json={"ids": [ids[1], ids[2], ids[0]]})
    assert resp.status_code == 200, resp.text
    assert _topic_names(resp.json()["modules"][0]) == ["B", "C", "A"]

    assert client.put(f"/modules/{module['id']}/topics/order", json={"ids": [ids[0]]}).status_code == 400

    assert client.delete(f"/topics/{ids[1]}").status_code == 204  # "B", first in order
    topics = _tree(client, course["id"])["modules"][0]["topics"]
    assert [t["name"] for t in topics] == ["C", "A"]
    assert [t["position"] for t in topics] == [0, 1]


def test_patch_topic_renames_and_moves_within_the_same_course(client, db_session):
    course = make_course(client, "Math")
    one = make_module(client, course["id"], "One")
    two = make_module(client, course["id"], "Two")
    a = client.post("/topics", json={"name": "A", "module_id": one["id"]}).json()
    b = client.post("/topics", json={"name": "B", "module_id": one["id"]}).json()
    c = client.post("/topics", json={"name": "C", "module_id": one["id"]}).json()
    client.post("/topics", json={"name": "X", "module_id": two["id"]})

    renamed = client.patch(f"/topics/{a['id']}", json={"name": "A2", "description": "new"})
    assert renamed.status_code == 200
    assert renamed.json()["name"] == "A2" and renamed.json()["description"] == "new"

    moved = client.patch(f"/topics/{a['id']}", json={"module_id": two["id"]})
    assert moved.status_code == 200, moved.text
    body = moved.json()
    assert (body["module_id"], body["module_name"], body["position"]) == (two["id"], "Two", 1)

    tree = _tree(client, course["id"])
    assert _topic_names(tree["modules"][0]) == ["B", "C"]
    assert [t["position"] for t in tree["modules"][0]["topics"]] == [0, 1]  # repacked
    assert _topic_names(tree["modules"][1]) == ["X", "A2"]

    # topics.user_id stays equal to the course owner.
    db_session.rollback()
    owner_id = db_session.get(models.Course, course["id"]).user_id
    assert {t.user_id for t in db_session.query(models.Topic).all()} == {owner_id}
    assert b["id"] and c["id"]


def test_topic_cannot_move_to_a_module_of_another_course(client):
    math = make_course(client, "Math")
    art = make_course(client, "Art")
    math_module = make_module(client, math["id"], "One")
    art_module = make_module(client, art["id"], "Gallery")
    topic = client.post("/topics", json={"name": "A", "module_id": math_module["id"]}).json()

    resp = client.patch(f"/topics/{topic['id']}", json={"module_id": art_module["id"]})
    assert resp.status_code == 400
    assert _topic_names(_tree(client, math["id"])["modules"][0]) == ["A"]


def test_topic_out_carries_module_and_course_context(client):
    topic = make_topic(client, "Hash Tables", course="DSA", module="Hashing")
    assert topic["module_name"] == "Hashing"
    assert topic["course_name"] == "DSA"
    assert topic["position"] == 0

    (listed,) = client.get("/topics").json()
    assert listed["course_id"] == topic["course_id"]
    assert client.get(f"/topics/{topic['id']}").json()["module_id"] == topic["module_id"]


# --- Cascades ----------------------------------------------------------------


def _add_topic_dependents(db_session, topic_id):
    """Give a topic one of everything that hangs off it."""
    source = models.Source(
        topic_id=topic_id, source_type=models.SourceType.self_supplied, title="notes", raw_text="x"
    )
    db_session.add(source)
    db_session.flush()
    db_session.add(
        models.Chunk(source_id=source.id, topic_id=topic_id, chunk_text="x", chunk_index=0)
    )
    db_session.add(models.StudySession(topic_id=topic_id, type=models.SessionType.quiz))
    quiz_set = models.QuizSet(topic_id=topic_id)
    quiz_set.questions.append(
        models.QuizQuestion(position=0, question_text="q", options={"A": "a"}, correct_option="A")
    )
    quiz_set.attempts.append(
        models.QuizAttempt(correct=1, total=1, score_percent=100.0, score_delta=10, answers={})
    )
    db_session.add(quiz_set)
    db_session.commit()


def _row_counts(db_session):
    return {
        model.__tablename__: _count(db_session, model)
        for model in (
            models.Course,
            models.Module,
            models.Topic,
            models.Mastery,
            models.Source,
            models.Chunk,
            models.StudySession,
            models.QuizSet,
            models.QuizQuestion,
            models.QuizAttempt,
            models.Prerequisite,
        )
    }


def test_deleting_a_course_removes_everything_under_it_and_nothing_else(client, db_session):
    keep = make_topic(client, "Keeper", course="Keep", module="K")
    _add_topic_dependents(db_session, keep["id"])
    after_keep = _row_counts(db_session)

    a = make_topic(client, "A", course="Doomed", module="One")
    b = make_topic(client, "B", course="Doomed", module="Two")
    for topic in (a, b):
        _add_topic_dependents(db_session, topic["id"])
    assert client.post(
        "/topics/prerequisites",
        json={"topic_id": b["id"], "prerequisite_topic_id": a["id"]},
    ).status_code == 200

    doomed_id = a["course_id"]
    assert _row_counts(db_session)["topics"] == 3

    assert client.delete(f"/courses/{doomed_id}").status_code == 204
    assert _row_counts(db_session) == after_keep


def test_deleting_a_module_cascades_and_clears_prerequisites_in_both_directions(
    client, db_session
):
    x = make_topic(client, "X", course="Math", module="Stays")
    y = make_topic(client, "Y", course="Math", module="Goes")
    z = make_topic(client, "Z", course="Math", module="Goes")
    for topic in (x, y, z):
        _add_topic_dependents(db_session, topic["id"])
    # X is a prerequisite of Y (X in, Y out) and Z is a prerequisite of X
    # (Z out, X in): the module delete must clear both rows.
    for topic_id, prereq_id in ((y["id"], x["id"]), (x["id"], z["id"])):
        resp = client.post(
            "/topics/prerequisites",
            json={"topic_id": topic_id, "prerequisite_topic_id": prereq_id},
        )
        assert resp.status_code == 200, resp.text
    assert _row_counts(db_session)["prerequisites"] == 2

    assert client.delete(f"/modules/{y['module_id']}").status_code == 204

    counts = _row_counts(db_session)
    assert counts["modules"] == 1
    assert counts["topics"] == 1
    assert counts["mastery"] == 1
    assert counts["sources"] == 1
    assert counts["chunks"] == 1
    assert counts["sessions"] == 1
    assert counts["quiz_sets"] == 1
    assert counts["quiz_questions"] == 1
    assert counts["quiz_attempts"] == 1
    assert counts["prerequisites"] == 0


def test_deleting_a_topic_cascades_and_clears_prerequisites_in_both_directions(
    client, db_session
):
    a = make_topic(client, "A")
    b = make_topic(client, "B")
    c = make_topic(client, "C")
    for topic in (a, b, c):
        _add_topic_dependents(db_session, topic["id"])
    # B depends on A, and C depends on B.
    for topic_id, prereq_id in ((b["id"], a["id"]), (c["id"], b["id"])):
        client.post(
            "/topics/prerequisites",
            json={"topic_id": topic_id, "prerequisite_topic_id": prereq_id},
        )

    assert client.delete(f"/topics/{b['id']}").status_code == 204

    counts = _row_counts(db_session)
    assert counts["topics"] == 2
    assert counts["mastery"] == 2
    assert counts["sources"] == 2
    assert counts["chunks"] == 2
    assert counts["sessions"] == 2
    assert counts["quiz_sets"] == 2
    assert counts["quiz_questions"] == 2
    assert counts["quiz_attempts"] == 2
    assert counts["prerequisites"] == 0


# --- Prerequisites -----------------------------------------------------------


def test_prerequisites_may_cross_modules_but_not_courses(client):
    a = make_topic(client, "A", course="Math", module="One")
    b = make_topic(client, "B", course="Math", module="Two")
    elsewhere = make_topic(client, "E", course="Art", module="Gallery")

    ok = client.post(
        "/topics/prerequisites", json={"topic_id": b["id"], "prerequisite_topic_id": a["id"]}
    )
    assert ok.status_code == 200, ok.text

    cross = client.post(
        "/topics/prerequisites",
        json={"topic_id": elsewhere["id"], "prerequisite_topic_id": a["id"]},
    )
    assert cross.status_code == 400
    assert "same course" in cross.json()["detail"]

    assert client.post(
        "/topics/prerequisites", json={"topic_id": a["id"], "prerequisite_topic_id": a["id"]}
    ).status_code == 400
    assert client.post(
        "/topics/prerequisites", json={"topic_id": b["id"], "prerequisite_topic_id": a["id"]}
    ).status_code == 400  # duplicate


# --- Graph -------------------------------------------------------------------


def test_graph_nodes_carry_module_info_and_can_be_filtered_by_course(client):
    a = make_topic(client, "A", course="Math", module="One")
    b = make_topic(client, "B", course="Math", module="Two")
    elsewhere = make_topic(client, "E", course="Art", module="Gallery")
    client.post(
        "/topics/prerequisites", json={"topic_id": b["id"], "prerequisite_topic_id": a["id"]}
    )

    everything = client.get("/topics/graph/json").json()
    assert {n["name"] for n in everything["nodes"]} == {"A", "B", "E"}

    math_graph = client.get(f"/topics/graph/json?course_id={a['course_id']}").json()
    assert {n["name"] for n in math_graph["nodes"]} == {"A", "B"}
    assert math_graph["edges"] == [{"source": a["id"], "target": b["id"]}]

    node_b = next(n for n in math_graph["nodes"] if n["name"] == "B")
    assert node_b["course_id"] == b["course_id"]
    assert node_b["module_id"] == b["module_id"]
    assert node_b["module_name"] == "Two"
    assert node_b["module_position"] == 1
    assert "course" not in node_b

    art_graph = client.get(f"/topics/graph/json?course_id={elsewhere['course_id']}").json()
    assert [n["name"] for n in art_graph["nodes"]] == ["E"]
    assert art_graph["edges"] == []


# --- Ownership ---------------------------------------------------------------


def test_other_users_resources_are_404_everywhere(client, other_client):
    topic = make_topic(client, "Secret", course="Mine", module="M")
    other_topic = make_topic(other_client, "Theirs", course="Theirs", module="TM")
    course_id, module_id, topic_id = topic["course_id"], topic["module_id"], topic["id"]

    requests = [
        ("get", f"/courses/{course_id}/tree", None),
        ("patch", f"/courses/{course_id}", {"name": "Stolen"}),
        ("delete", f"/courses/{course_id}", None),
        ("post", f"/courses/{course_id}/modules", {"name": "Injected"}),
        ("put", f"/courses/{course_id}/modules/order", {"ids": [module_id]}),
        ("patch", f"/modules/{module_id}", {"name": "Stolen"}),
        ("delete", f"/modules/{module_id}", None),
        ("put", f"/modules/{module_id}/topics/order", {"ids": [topic_id]}),
        ("post", "/topics", {"name": "Injected", "module_id": module_id}),
        ("get", f"/topics/{topic_id}", None),
        ("patch", f"/topics/{topic_id}", {"name": "Stolen"}),
        ("delete", f"/topics/{topic_id}", None),
        ("get", f"/topics/graph/json?course_id={course_id}", None),
        (
            "post",
            "/topics/prerequisites",
            {"topic_id": other_topic["id"], "prerequisite_topic_id": topic_id},
        ),
    ]
    for method, path, body in requests:
        resp = getattr(other_client, method)(path, **({"json": body} if body is not None else {}))
        assert resp.status_code == 404, f"{method.upper()} {path} -> {resp.status_code}"

    # Moving your own topic into someone else's module is a 404 too.
    resp = other_client.patch(
        f"/topics/{other_topic['id']}", json={"module_id": module_id}
    )
    assert resp.status_code == 404

    # And none of it changed anything.
    tree = _tree(client, course_id)
    assert tree["name"] == "Mine"
    assert _module_names(tree) == ["M"]
    assert _topic_names(tree["modules"][0]) == ["Secret"]


def test_lists_only_include_the_callers_own_data(client, other_client):
    make_topic(client, "Mine", course="Mine")
    make_topic(other_client, "Theirs", course="Theirs")

    assert [c["name"] for c in client.get("/courses").json()] == ["Mine"]
    assert [t["name"] for t in client.get("/topics").json()] == ["Mine"]
    assert [n["name"] for n in client.get("/topics/graph/json").json()["nodes"]] == ["Mine"]


def test_courses_without_an_owner_are_invisible_to_every_account(client, db_session):
    orphan = models.Course(user_id=None, name="Unowned")
    db_session.add(orphan)
    db_session.commit()

    assert client.get("/courses").json() == []
    assert client.get(f"/courses/{orphan.id}/tree").status_code == 404
    assert client.delete(f"/courses/{orphan.id}").status_code == 404


def test_course_routes_require_auth():
    from app.main import app

    bare = TestClient(app)
    assert bare.get("/courses").status_code == 401
    assert bare.post("/courses", json={"name": "X"}).status_code == 401
    assert bare.get("/courses/1/tree").status_code == 401
    assert bare.patch("/modules/1", json={"name": "X"}).status_code == 401
    assert bare.delete("/topics/1").status_code == 401
