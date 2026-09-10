import networkx as nx
from sqlalchemy.orm import Session

from app.models import Mastery, MasteryStatus, Prerequisite, Topic


def build_graph(db: Session) -> nx.DiGraph:
    """Reconstruct the prerequisite DiGraph from Postgres.

    Edges point from prerequisite_topic_id -> topic_id (i.e. "must be
    learned before"), so descendants of a node are the topics that depend
    on it.
    """
    graph = nx.DiGraph()

    for topic in db.query(Topic).all():
        graph.add_node(topic.id, name=topic.name, course=topic.course)

    for prereq in db.query(Prerequisite).all():
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


def get_topic_order(db: Session) -> list[Topic]:
    graph = build_graph(db)
    try:
        ordered_ids = list(nx.topological_sort(graph))
    except nx.NetworkXUnfeasible:
        ordered_ids = [t.id for t in db.query(Topic).all()]

    topics_by_id = {t.id: t for t in db.query(Topic).all()}
    return [topics_by_id[tid] for tid in ordered_ids if tid in topics_by_id]


def get_graph_json(db: Session) -> dict:
    topics = db.query(Topic).all()
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
        {"source": p.prerequisite_topic_id, "target": p.topic_id} for p in prereqs
    ]

    return {"nodes": nodes, "edges": edges}
