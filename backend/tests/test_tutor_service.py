import pytest

from app.config import RETRIEVAL_RELEVANCE_THRESHOLD
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


def test_only_chunks_at_or_above_the_threshold_are_cited(monkeypatch):
    prompts = []

    def fake_generate(system, user, model=None):
        prompts.append(user)
        return llm_service.LLMResult(ok=True, text="An answer.")

    monkeypatch.setattr(llm_service, "generate", fake_generate)

    retrieved = [
        {"source": "A.pdf", "page": 1, "text": "Strong match text.", "similarity": 0.80},
        {"source": "B.pdf", "page": 2, "text": "Borderline text.", "similarity": RETRIEVAL_RELEVANCE_THRESHOLD},
        {"source": "C.pdf", "page": 3, "text": "Weak match text.", "similarity": RETRIEVAL_RELEVANCE_THRESHOLD - 0.01},
        {"source": "D.pdf", "page": None, "text": "Noise text.", "similarity": 0.05},
    ]
    result = generate_tutor_answer(
        question="Q?",
        retrieved_chunks=retrieved,
        topic_name="T",
        topic_mastery_score=50,
        prerequisite_gaps=[],
    )

    assert result.grounded is True
    assert result.sources == [{"source": "A.pdf", "page": 1}, {"source": "B.pdf", "page": 2}]
    # The prompt context is unchanged: every retrieved chunk is still given to the model.
    assert all(text in prompts[0] for text in ("Strong match", "Borderline", "Weak match", "Noise"))


def test_the_answer_gate_still_uses_only_the_top_match(monkeypatch):
    monkeypatch.setattr(
        llm_service, "generate", lambda system, user, model=None: llm_service.LLMResult(ok=True, text="ok")
    )
    # Best match is below the threshold -> no answer and no citations at all.
    below = [{"source": "A.pdf", "page": 1, "text": "x", "similarity": RETRIEVAL_RELEVANCE_THRESHOLD - 0.1}]
    result = generate_tutor_answer("Q?", below, "T", 50, [])
    assert result.grounded is False and result.sources == []


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
