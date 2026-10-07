"""Shared builders for tests that need a Course -> Module -> Topic chain."""


def make_course(client, name="Test Course", description=None):
    """Create a course (or return the existing one with that name)."""
    for course in client.get("/courses").json():
        if course["name"] == name:
            return course
    resp = client.post("/courses", json={"name": name, "description": description})
    assert resp.status_code == 200, resp.text
    return resp.json()


def make_module(client, course_id, name="Module 1"):
    """Create a module in the course (or return the existing one with that name)."""
    tree = client.get(f"/courses/{course_id}/tree").json()
    for module in tree["modules"]:
        if module["name"] == name:
            return module
    resp = client.post(f"/courses/{course_id}/modules", json={"name": name})
    assert resp.status_code == 200, resp.text
    return resp.json()


def make_topic(client, name, course="Test Course", module="Module 1", description=""):
    """Create a topic, creating its course and module on demand. Returns the
    topic JSON."""
    course_json = make_course(client, course)
    module_json = make_module(client, course_json["id"], module)
    resp = client.post(
        "/topics",
        json={"name": name, "module_id": module_json["id"], "description": description},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


_SENTENCE_TEMPLATES = [
    "A hash table maps key number {n} to a bucket by applying a hash function to it.",
    "When two keys such as {n} and {m} land in the same bucket, the table must resolve the collision.",
    "Chaining keeps a linked list of entries in each bucket, so lookup number {n} walks that list.",
    "Open addressing instead probes other slots, and the load factor {n} percent controls how often it must.",
    "Resizing the table to {m} buckets rehashes every stored key, which is why it is done rarely.",
    "The average cost of an insertion stays constant while the worst case degrades to linear time.",
]


def distinct_prose(sentences: int) -> str:
    """Prose of `sentences` sentences, none identical to another (each carries its
    own numbers), in paragraphs of five. Deterministic."""
    out = []
    for i in range(sentences):
        template = _SENTENCE_TEMPLATES[i % len(_SENTENCE_TEMPLATES)]
        out.append(template.format(n=i, m=i * 7 + 3))
    paragraphs = [" ".join(out[j : j + 5]) for j in range(0, len(out), 5)]
    return "\n\n".join(paragraphs)
