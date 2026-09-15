import pytest

from app.services import llm_service
from app.services.tutor_service import explanation_depth_for_score, generate_tutor_answer


@pytest.mark.parametrize(
    "score,expected",
    [(0, "low"), (39, "low"), (40, "medium"), (79, "medium"), (80, "high"), (100, "high")],
)
def test_explanation_depth_boundaries(score, expected):
    assert explanation_depth_for_score(score) == expected


def test_below_threshold_never_calls_the_llm(monkeypatch):
    def _fail_if_called(*args, **kwargs):
        raise AssertionError("llm_service.generate should not be called for weak retrieval")

    monkeypatch.setattr(llm_service, "generate", _fail_if_called)

    result = generate_tutor_answer(
        question="Something unrelated",
        retrieved_chunks=[{"source": "notes.pdf", "page": 1, "text": "irrelevant", "similarity": 0.05}],
        topic_name="Topic",
        topic_mastery_score=50,
        prerequisite_gaps=[],
    )

    assert result.grounded is False
    assert "couldn't find enough information" in result.answer
    assert result.sources == []


def test_no_retrieved_chunks_at_all_is_also_insufficient(monkeypatch):
    monkeypatch.setattr(
        llm_service, "generate", lambda *a, **k: (_ for _ in ()).throw(AssertionError("should not be called"))
    )
    result = generate_tutor_answer(
        question="Q", retrieved_chunks=[], topic_name="Topic", topic_mastery_score=50, prerequisite_gaps=[]
    )
    assert result.grounded is False


def test_successful_answer_carries_citations_only_from_retrieved_chunks(monkeypatch):
    monkeypatch.setattr(
        llm_service,
        "generate",
        lambda system, user, model=None: llm_service.LLMResult(ok=True, text="A real grounded answer."),
    )

    retrieved = [
        {"source": "DBMS_Module2.pdf", "page": 7, "text": "3NF removes transitive dependencies.", "similarity": 0.8},
        {"source": "DBMS_Module2.pdf", "page": 9, "text": "More on normal forms.", "similarity": 0.6},
    ]

    result = generate_tutor_answer(
        question="Explain 3NF",
        retrieved_chunks=retrieved,
        topic_name="Normalization",
        topic_mastery_score=50,
        prerequisite_gaps=[{"name": "Functional Dependency", "score": 35}],
    )

    assert result.grounded is True
    assert result.answer == "A real grounded answer."
    assert result.sources == [
        {"source": "DBMS_Module2.pdf", "page": 7},
        {"source": "DBMS_Module2.pdf", "page": 9},
    ]


def test_llm_failure_returns_graceful_fallback_not_a_crash(monkeypatch):
    monkeypatch.setattr(
        llm_service,
        "generate",
        lambda system, user, model=None: llm_service.LLMResult(ok=False, error="Ollama is not running or unreachable."),
    )

    result = generate_tutor_answer(
        question="Explain 3NF",
        retrieved_chunks=[{"source": "notes.pdf", "page": 1, "text": "3NF content", "similarity": 0.9}],
        topic_name="Normalization",
        topic_mastery_score=50,
        prerequisite_gaps=[],
    )

    assert result.grounded is False
    assert "Ollama is not running" in result.answer
    assert result.sources == []
