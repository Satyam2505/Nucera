"""What to study next in a course, from the prerequisite graph and the topics' mastery.

Deterministic and explained: every suggestion carries a plain-language reason, and no
model is involved. The order:

1. Reviews first: topics that were learned but have faded enough to be due
   (services/mastery_model.py), the most overdue first.
2. Then topics that are ready: not yet mastered, with every direct prerequisite
   mastered. Among them, topics marked "missed" or flagged for revision come first, then
   the ones that unlock the most other topics, then course order.

Topics that are blocked by an unmastered prerequisite are not listed: whatever they wait
on is always listed first (every chain of prerequisites starts at a ready topic), so a
"blocked" entry would only repeat it. A legacy loop of prerequisites, where nothing is
ever ready, falls back to course order rather than suggesting nothing.
"""

from datetime import datetime
from typing import Dict, List, Optional

import networkx as nx
from sqlalchemy.orm import Session

from app import models
from app.services import graph_service, mastery_model


def _plural(n: int, word: str) -> str:
    return f"{n} {word}" if n == 1 else f"{n} {word}s"


def _review_reason(overdue_days: float) -> str:
    whole = int(overdue_days)
    if whole < 1:
        return "Due for review: it has started to fade"
    return f"Due for review: {_plural(whole, 'day')} overdue"


def next_steps(
    db: Session,
    user_id: int,
    course_id: int,
    limit: int = 3,
    now: Optional[datetime] = None,
) -> List[dict]:
    now = now or datetime.utcnow()
    topics = graph_service.topic_query(db, user_id, course_id).all()
    if not topics:
        return []

    ids = {t.id for t in topics}
    graph = graph_service.build_graph(db, user_id)
    course_graph = graph.subgraph(ids)
    mastery_by_topic: Dict[int, models.Mastery] = {
        m.topic_id: m for m in db.query(models.Mastery).filter(models.Mastery.topic_id.in_(ids)).all()
    }

    def status_of(topic_id: int) -> models.MasteryStatus:
        m = mastery_by_topic.get(topic_id)
        return m.status if m is not None else models.MasteryStatus.unmastered

    def score_of(topic_id: int) -> int:
        m = mastery_by_topic.get(topic_id)
        return m.score if m is not None else 0

    def item(topic: models.Topic, kind: str, reason: str) -> dict:
        m = mastery_by_topic.get(topic.id)
        return {
            "topic_id": topic.id,
            "topic_name": topic.name,
            "module_name": topic.module.name,
            "kind": kind,
            "reason": reason,
            "score": score_of(topic.id),
            "status": status_of(topic.id).value,
            "due_for_review": bool(m is not None and mastery_model.is_due_for_review(m, now)),
        }

    mastered = models.MasteryStatus.mastered
    reading_order = {t.id: i for i, t in enumerate(topics)}

    # 1. Learned but faded: due for review, most overdue first.
    due = [
        t
        for t in topics
        if t.id in mastery_by_topic and mastery_model.is_due_for_review(mastery_by_topic[t.id], now)
    ]
    due.sort(key=lambda t: (-mastery_model.days_overdue(mastery_by_topic[t.id], now), reading_order[t.id]))
    steps = [
        item(t, "review", _review_reason(mastery_model.days_overdue(mastery_by_topic[t.id], now)))
        for t in due
    ]
    already = {t.id for t in due}

    # 2. Ready: not mastered, every direct prerequisite mastered.
    ready = [
        t
        for t in topics
        if t.id not in already
        and status_of(t.id) != mastered
        and all(status_of(p) == mastered for p in course_graph.predecessors(t.id))
    ]

    def unlocks(topic_id: int) -> int:
        return len(nx.descendants(course_graph, topic_id))

    def needs_attention(topic_id: int) -> bool:
        m = mastery_by_topic.get(topic_id)
        return m is not None and (
            m.status == models.MasteryStatus.missed or bool(m.flagged_for_revision)
        )

    ready.sort(
        key=lambda t: (
            0 if needs_attention(t.id) else 1,
            -unlocks(t.id),
            t.module.position,
            t.position,
            reading_order[t.id],
        )
    )
    for t in ready:
        parts = []
        m = mastery_by_topic.get(t.id)
        if m is not None and m.status == models.MasteryStatus.missed:
            parts.append("Marked as missed")
        elif m is not None and m.flagged_for_revision:
            parts.append("Flagged for revision")
        n = unlocks(t.id)
        if n:
            parts.append(f"Unlocks {_plural(n, 'topic')}")
        if score_of(t.id) > 0:
            parts.append(f"In progress ({score_of(t.id)}%)")
        steps.append(item(t, "ready", ". ".join(parts) if parts else "Next in the course"))

    # A loop in old data can leave nothing ready: fall back to course order.
    if not steps:
        for t in topics:
            if status_of(t.id) != mastered:
                steps.append(item(t, "ready", "Next in the course"))

    return steps[:limit]
