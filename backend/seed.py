import argparse
import sys
from typing import Optional

from app import models
from app.database import Base, SessionLocal, engine

COURSE_NAME = "Data Structures & Algorithms"
COURSE_DESCRIPTION = "Core data structures and the algorithms that operate on them."

# (module name, [(topic name, description), ...]) in reading order.
MODULES = [
    (
        "Foundations",
        [
            ("Sets and Functions", "Basic set theory and function notation."),
            ("Big-O Notation", "Analyzing algorithm time and space complexity."),
        ],
    ),
    (
        "Linear Structures",
        [
            ("Arrays and Strings", "Contiguous memory structures and string manipulation."),
            ("Linked Lists", "Singly and doubly linked list structures and operations."),
            ("Stacks and Queues", "LIFO and FIFO abstract data types."),
        ],
    ),
    (
        "Recursion and Trees",
        [
            ("Recursion", "Solving problems via self-referential functions."),
            ("Trees and Binary Search Trees", "Hierarchical structures and ordered tree traversal."),
            ("Graphs", "Graph representations and traversal algorithms (BFS/DFS)."),
        ],
    ),
    (
        "Hashing and Sorting",
        [
            ("Hash Tables", "Key-value storage using hashing for O(1) average access."),
            ("Sorting Algorithms", "Comparison and non-comparison based sorting techniques."),
        ],
    ),
]

# topic_name -> list of prerequisite topic names
PREREQUISITES = {
    "Big-O Notation": ["Sets and Functions"],
    "Arrays and Strings": ["Big-O Notation"],
    "Linked Lists": ["Arrays and Strings"],
    "Stacks and Queues": ["Linked Lists"],
    "Recursion": ["Big-O Notation"],
    "Trees and Binary Search Trees": ["Recursion", "Linked Lists"],
    "Graphs": ["Trees and Binary Search Trees"],
    "Hash Tables": ["Arrays and Strings"],
    "Sorting Algorithms": ["Arrays and Strings", "Recursion"],
}


def seed(email: Optional[str] = None):
    """Seed the sample course. With `email`, the course belongs to that
    existing account; without it the course has no owner (and so is not
    visible to any logged-in user).
    """
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        owner_id = None
        if email:
            user = db.query(models.User).filter(models.User.email == email).first()
            if user is None:
                sys.exit(f"No account with email {email!r}. Register it first, then re-run.")
            owner_id = user.id

        owned_by = (
            models.Course.user_id == owner_id
            if owner_id is not None
            else models.Course.user_id.is_(None)
        )
        existing = (
            db.query(models.Course).filter(models.Course.name == COURSE_NAME, owned_by).first()
        )
        if existing:
            print(f"Course {COURSE_NAME!r} already exists for this owner; skipping seed.")
            return

        course = models.Course(
            user_id=owner_id, name=COURSE_NAME, description=COURSE_DESCRIPTION
        )
        db.add(course)
        db.flush()

        topics_by_name = {}
        for module_position, (module_name, topics) in enumerate(MODULES):
            module = models.Module(
                course_id=course.id, name=module_name, position=module_position
            )
            db.add(module)
            db.flush()
            for topic_position, (name, description) in enumerate(topics):
                topic = models.Topic(
                    module_id=module.id,
                    user_id=owner_id,
                    name=name,
                    description=description,
                    position=topic_position,
                )
                db.add(topic)
                db.flush()
                topics_by_name[name] = topic
                db.add(models.Mastery(topic_id=topic.id))

        for topic_name, prereq_names in PREREQUISITES.items():
            topic = topics_by_name[topic_name]
            for prereq_name in prereq_names:
                db.add(
                    models.Prerequisite(
                        topic_id=topic.id,
                        prerequisite_topic_id=topics_by_name[prereq_name].id,
                    )
                )

        db.commit()
        owner = f"account {email}" if email else "no owner"
        print(
            f"Seeded course {COURSE_NAME!r}: {len(MODULES)} modules, "
            f"{len(topics_by_name)} topics ({owner})."
        )
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed the sample course.")
    parser.add_argument(
        "--email",
        help="attach the seeded course to this existing account "
        "(otherwise it has no owner and no one can see it)",
    )
    seed(parser.parse_args().email)
