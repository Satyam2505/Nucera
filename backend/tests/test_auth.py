"""Real tests for registration, login, and topic ownership scoping.

Uses a bare (unauthenticated) TestClient here rather than the `client`
fixture, since that fixture is pre-authenticated as a fixed test user —
these tests need to control registration/login themselves, and some
need a *second* independent user to prove data isolation.
"""
from fastapi.testclient import TestClient

from app.main import app


def _raw_client():
    return TestClient(app)


def test_register_creates_a_user_and_rejects_duplicate_email():
    client = _raw_client()
    resp = client.post("/auth/register", json={"email": "alice@example.com", "password": "hunter22"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["email"] == "alice@example.com"
    assert "id" in body
    assert "password" not in body and "hashed_password" not in body

    dupe = client.post("/auth/register", json={"email": "alice@example.com", "password": "somethingelse"})
    assert dupe.status_code == 400


def test_login_succeeds_with_correct_password_and_fails_with_wrong_one():
    client = _raw_client()
    client.post("/auth/register", json={"email": "bob@example.com", "password": "correct-horse"})

    good = client.post("/auth/login", data={"username": "bob@example.com", "password": "correct-horse"})
    assert good.status_code == 200, good.text
    assert good.json()["token_type"] == "bearer"
    assert good.json()["access_token"]

    bad = client.post("/auth/login", data={"username": "bob@example.com", "password": "wrong-password"})
    assert bad.status_code == 401


def test_me_endpoint_requires_a_valid_token():
    client = _raw_client()
    no_token = client.get("/auth/me")
    assert no_token.status_code == 401

    client.post("/auth/register", json={"email": "carol@example.com", "password": "password123"})
    login = client.post("/auth/login", data={"username": "carol@example.com", "password": "password123"})
    token = login.json()["access_token"]

    ok = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert ok.status_code == 200
    assert ok.json()["email"] == "carol@example.com"

    bad_token = client.get("/auth/me", headers={"Authorization": "Bearer not-a-real-token"})
    assert bad_token.status_code == 401


def test_topics_endpoint_requires_auth():
    client = _raw_client()
    resp = client.get("/topics")
    assert resp.status_code == 401


def _token_for(client, email, password):
    client.post("/auth/register", json={"email": email, "password": password})
    login = client.post("/auth/login", data={"username": email, "password": password})
    return login.json()["access_token"]


def test_users_only_see_their_own_topics():
    client = _raw_client()
    token_a = _token_for(client, "dave@example.com", "password123")
    token_b = _token_for(client, "erin@example.com", "password123")

    create_resp = client.post(
        "/topics",
        json={"name": "Dave's Topic", "course": "Course A", "description": ""},
        headers={"Authorization": f"Bearer {token_a}"},
    )
    assert create_resp.status_code == 200, create_resp.text
    dave_topic_id = create_resp.json()["id"]

    dave_list = client.get("/topics", headers={"Authorization": f"Bearer {token_a}"})
    assert [t["id"] for t in dave_list.json()] == [dave_topic_id]

    erin_list = client.get("/topics", headers={"Authorization": f"Bearer {token_b}"})
    assert erin_list.json() == []

    # Erin can't fetch Dave's topic by id either, even knowing its id.
    erin_get = client.get(f"/topics/{dave_topic_id}", headers={"Authorization": f"Bearer {token_b}"})
    assert erin_get.status_code == 404
