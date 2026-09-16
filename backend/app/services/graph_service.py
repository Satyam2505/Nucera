from typing import Optional

import networkx as nx
from sqlalchemy.orm import Session

from app.models import Mastery, MasteryStatus, Prerequisite, Topic


def build_graph(db: Session, user_id: Optional[int] = None) -> nx.DiGraph:
    """Reconstruct the prerequisite DiGraph from the database.

    Edges point from prerequisite_topic_id -> topic_id (i.e. "must be
    learned before"), so descendants of a node are the topics that depend
    on it. When user_id is given, only that user's topics (and the
    prerequisite edges between them) are included.
    """
    graph = nx.DiGraph()

    topic_query = db.query(Topic)
    if user_id is not None:
        topic_query = topic_query.filter(Topic.user_id == user_id)
    topic_ids = set()
    for topic in topic_query.all():
        graph.add_node(topic.id, name=topic.name, course=topic.course)
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

    topic_query = db.query(Topic)
    if user_id is not None:
        topic_query = topic_query.filter(Topic.user_id == user_id)
    topics_by_id = {t.id: t for t in topic_query.all()}
    return [topics_by_id[tid] for tid in ordered_ids if tid in topics_by_id]


def get_graph_json(db: Session, user_id: Optional[int] = None) -> dict:
    topic_query = db.query(Topic)
    if user_id is not None:
        topic_query = topic_query.filter(Topic.user_id == user_id)
    topics = topic_query.all()
    topic_ids = {t.id for t in topics}

    mastery_by_topic = {m.topic_id: m for m in db.query(Mastery).all()}
    prereqs = db.query(Prerequisite).all()

    nodes = [
        {
            "id": topic.id,
            "name": topic.name,
            "course": topic.course,
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
        if user_id is None or (p.prerequisite_topic_id in topic_ids and p.topic_id in topic_ids)
    ]

    return {"nodes": nodes, "edges": edges}
