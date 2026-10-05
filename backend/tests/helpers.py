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
