from app import models
from app.database import Base, SessionLocal, engine

TOPICS = [
    ("Sets and Functions", "Data Structures & Algorithms", "Basic set theory and function notation."),
    ("Big-O Notation", "Data Structures & Algorithms", "Analyzing algorithm time and space complexity."),
    ("Arrays and Strings", "Data Structures & Algorithms", "Contiguous memory structures and string manipulation."),
    ("Linked Lists", "Data Structures & Algorithms", "Singly and doubly linked list structures and operations."),
    ("Stacks and Queues", "Data Structures & Algorithms", "LIFO and FIFO abstract data types."),
    ("Recursion", "Data Structures & Algorithms", "Solving problems via self-referential functions."),
    ("Trees and Binary Search Trees", "Data Structures & Algorithms", "Hierarchical structures and ordered tree traversal."),
    ("Graphs", "Data Structures & Algorithms", "Graph representations and traversal algorithms (BFS/DFS)."),
    ("Hash Tables", "Data Structures & Algorithms", "Key-value storage using hashing for O(1) average access."),
    ("Sorting Algorithms", "Data Structures & Algorithms", "Comparison and non-comparison based sorting techniques."),
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


def seed():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        if db.query(models.Topic).count():
            print("Database already has topics; skipping seed.")
            return

        topics_by_name = {}
        for name, course, description in TOPICS:
            topic = models.Topic(name=name, course=course, description=description)
            db.add(topic)
            db.flush()
            topics_by_name[name] = topic
            db.add(models.Mastery(topic_id=topic.id))

        db.commit()

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
        print(f"Seeded {len(TOPICS)} topics for course 'Data Structures & Algorithms'.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
