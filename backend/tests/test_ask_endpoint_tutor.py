from app.services import llm_service


def _create_topic(client, name, course="Test Course"):
    resp = client.post("/topics", json={"name": name, "course": course, "description": ""})
    assert resp.status_code == 200, resp.text
    return resp.json()["id"]


def test_ask_returns_grounded_answer_with_sources_when_llm_succeeds(client, monkeypatch):
    monkeypatch.setattr(
        llm_service,
        "generate",
        lambda system, user, model=None: llm_service.LLMResult(
            ok=True, text="Hash tables map keys to values using a hash function."
        ),
    )

    topic_id = _create_topic(client, "Hash Tables")
    client.post(
        "/sources/text",
        json={
            "topic_id": topic_id,
            "source_type": "self_supplied",
            "title": "Hash table notes",
            "text": "A hash table maps keys to values using a hash function to compute a bucket index.",
        },
    )

    resp = client.post("/ask", json={"query": "What is a hash table?", "topic_id": topic_id})
    assert resp.status_code == 200, resp.text
    body = resp.json()

    assert body["grounded"] is True
    assert body["answer"] == "Hash tables map keys to values using a hash function."
    assert body["sources"]
    assert body["sources"][0]["source"] == "Hash table notes"


def test_ask_still_flags_prerequisite_gaps_alongside_the_real_answer(client, monkeypatch):
    monkeypatch.setattr(
        llm_service,
        "generate",
        lambda system, user, model=None: llm_service.LLMResult(ok=True, text="An answer."),
    )

    prereq_topic = _create_topic(client, "Sets", course="DS&A")
    main_topic_resp = client.post(
        "/topics", json={"name": "Hash Tables 2", "course": "DS&A", "description": ""}
    )
    main_topic = main_topic_resp.json()["id"]
    client.post(
        "/topics/prerequisites",
        json={"topic_id": main_topic, "prerequisite_topic_id": prereq_topic},
    )
    client.post(
        "/sources/text",
        json={
            "topic_id": main_topic,
            "source_type": "self_supplied",
            "title": "Notes",
            "text": "A hash table maps keys to values using a hash function.",
        },
    )

    resp = client.post("/ask", json={"query": "How do hash tables work?", "topic_id": main_topic})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert [t["name"] for t in body["flagged_prerequisites"]] == ["Sets"]


def test_ask_returns_insufficient_material_without_calling_llm_when_nothing_uploaded(client, monkeypatch):
    def _fail_if_called(*args, **kwargs):
        raise AssertionError("LLM should not be called when there is no material to ground on")

    monkeypatch.setattr(llm_service, "generate", _fail_if_called)

    topic_id = _create_topic(client, "Empty Topic")
    resp = client.post("/ask", json={"query": "Explain anything", "topic_id": topic_id})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["grounded"] is False
    assert "couldn't find enough information" in body["answer"]


def test_ask_degrades_gracefully_when_local_model_is_unavailable(client, monkeypatch):
    monkeypatch.setattr(
        llm_service,
        "generate",
        lambda system, user, model=None: llm_service.LLMResult(
            ok=False, error="Ollama is not running or unreachable."
        ),
    )

    topic_id = _create_topic(client, "Hash Tables 3")
    client.post(
        "/sources/text",
        json={
            "topic_id": topic_id,
            "source_type": "self_supplied",
            "title": "Notes",
            "text": "A hash table maps keys to values using a hash function.",
        },
    )

    resp = client.post("/ask", json={"query": "What is a hash table?", "topic_id": topic_id})
    assert resp.status_code == 200, resp.text  # API must not crash
    body = resp.json()
    assert body["grounded"] is False
    assert "Ollama is not running" in body["answer"]
