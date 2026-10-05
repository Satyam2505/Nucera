from typing import Optional

import networkx as nx
from sqlalchemy.orm import Query, Session, contains_eager

from app.models import Course, Mastery, MasteryStatus, Module, Prerequisite, Topic


def topic_query(db: Session, user_id: Optional[int], course_id: Optional[int] = None) -> Query:
    """Topics in reading order (course, module, position), optionally limited
    to one user's courses and/or a single course. Ownership resolves through
    course.user_id, matching app/ownership.py.
    """
    query = (
        db.query(Topic)
        .join(Module, Topic.module_id == Module.id)
        .join(Course, Module.course_id == Course.id)
        .options(contains_eager(Topic.module).contains_eager(Module.course))
        .order_by(Course.id, Module.position, Topic.position)
    )
    if user_id is not None:
        query = query.filter(Course.user_id == user_id)
    if course_id is not None:
        query = query.filter(Course.id == course_id)
    return query


def build_graph(db: Session, user_id: Optional[int] = None) -> nx.DiGraph:
    """Reconstruct the prerequisite DiGraph from the database.

    Edges point from prerequisite_topic_id -> topic_id (i.e. "must be
    learned before"), so descendants of a node are the topics that depend
    on it. When user_id is given, only that user's topics (and the
    prerequisite edges between them) are included.
    """
    graph = nx.DiGraph()

    topic_ids = set()
    for topic in topic_query(db, user_id).all():
        graph.add_node(topic.id, name=topic.name, module_id=topic.module_id)
        topic_ids.add(topic.id)

    for prereq in db.query(Prerequisite).all():
        if user_id is not None and (
            prereq.prerequisite_topic_id not in topic_ids or prereq.topic_id not in topic_ids
        ):
            continue
        graph.add_edge(prereq.prerequisite_topic_id, prereq.topic_id)

    return graph


def get_unmastered_prerequisites(db: Session, topic_id: int) -> list[Topic]:
    graph = build_graph(db)
    if topic_id not in graph:
        return []

    ancestor_ids = nx.ancestors(graph, topic_id)
    if not ancestor_ids:
        return []

    mastery_by_topic = {
        m.topic_id: m
        for m in db.query(Mastery).filter(Mastery.topic_id.in_(ancestor_ids)).all()
    }

    unmastered_ids = [
        ancestor_id
        for ancestor_id in ancestor_ids
        if mastery_by_topic.get(ancestor_id) is None
        or mastery_by_topic[ancestor_id].status != MasteryStatus.mastered
    ]

    return db.query(Topic).filter(Topic.id.in_(unmastered_ids)).all()


def get_topic_order(db: Session, user_id: Optional[int] = None) -> list[Topic]:
    graph = build_graph(db, user_id=user_id)
    try:
        ordered_ids = list(nx.topological_sort(graph))
    except nx.NetworkXUnfeasible:
        ordered_ids = list(graph.nodes)

    topics_by_id = {t.id: t for t in topic_query(db, user_id).all()}
    return [topics_by_id[tid] for tid in ordered_ids if tid in topics_by_id]


def get_graph_json(
    db: Session, user_id: Optional[int] = None, course_id: Optional[int] = None
) -> dict:
    topics = topic_query(db, user_id, course_id).all()
    topic_ids = {t.id for t in topics}

    mastery_by_topic = {
        m.topic_id: m
        for m in db.query(Mastery).filter(Mastery.topic_id.in_(topic_ids)).all()
    }
    prereqs = db.query(Prerequisite).filter(Prerequisite.topic_id.in_(topic_ids)).all()

    nodes = [
        {
            "id": topic.id,
            "name": topic.name,
            "course_id": topic.module.course_id,
            "module_id": topic.module_id,
            "module_name": topic.module.name,
            "module_position": topic.module.position,
            "status": (
                mastery_by_topic[topic.id].status.value
                if topic.id in mastery_by_topic
                else MasteryStatus.unmastered.value
            ),
            "score": mastery_by_topic[topic.id].score if topic.id in mastery_by_topic else 0,
        }
        for topic in topics
    ]

    edges = [
        {"source": p.prerequisite_topic_id, "target": p.topic_id}
        for p in prereqs
        if p.prerequisite_topic_id in topic_ids
    ]

    return {"nodes": nodes, "edges": edges}
