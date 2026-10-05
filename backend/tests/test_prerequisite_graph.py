from app import models
from app.services import graph_service


def test_get_unmastered_prerequisites_still_works_after_retrieval_changes(db_session):
    course = models.Course(name="C")
    module = models.Module(course=course, name="M", position=0)
    a = models.Topic(module=module, name="A", position=0)
    b = models.Topic(module=module, name="B", position=1)
    db_session.add_all([course, module, a, b])
    db_session.commit()
    db_session.refresh(a)
    db_session.refresh(b)

    db_session.add(models.Prerequisite(topic_id=b.id, prerequisite_topic_id=a.id))
    db_session.add(models.Mastery(topic_id=a.id, score=0))
    db_session.add(models.Mastery(topic_id=b.id, score=0))
    db_session.commit()

    unmastered = graph_service.get_unmastered_prerequisites(db_session, b.id)
    assert [t.name for t in unmastered] == ["A"]

    mastery_a = db_session.get(models.Mastery, a.id)
    mastery_a.status = models.MasteryStatus.mastered
    db_session.commit()

    assert graph_service.get_unmastered_prerequisites(db_session, b.id) == []
