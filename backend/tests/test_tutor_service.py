import pytest

from app.config import OLLAMA_MAX_OUTPUT_TOKENS, RETRIEVAL_RELEVANCE_THRESHOLD
from app.services import llm_service
from app.services.context_budget import estimate_tokens, prompt_token_budget, user_prompt_char_budget
from app.services.prompt_builder import SYSTEM_PROMPT
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


def test_only_chunks_at_or_above_the_threshold_reach_the_model_and_the_citations(monkeypatch):
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
    # The model is shown exactly what is cited: the chunks below the threshold
    # came back from search but are not given to it.
    assert "Strong match" in prompts[0] and "Borderline" in prompts[0]
    assert "Weak match" not in prompts[0] and "Noise" not in prompts[0]


def test_relevant_chunks_are_sent_best_first_even_if_passed_out_of_order(monkeypatch):
    prompts = []
    monkeypatch.setattr(
        llm_service,
        "generate",
        lambda system, user, model=None: prompts.append(user) or llm_service.LLMResult(ok=True, text="ok"),
    )
    retrieved = [
        {"source": "Low.pdf", "page": 1, "text": "second best", "similarity": 0.5},
        {"source": "High.pdf", "page": 2, "text": "best", "similarity": 0.9},
    ]
    result = generate_tutor_answer("Q?", retrieved, "T", 50, [])
    assert result.sources == [{"source": "High.pdf", "page": 2}, {"source": "Low.pdf", "page": 1}]
    assert prompts[0].index("best") < prompts[0].index("second best")


def test_a_chunk_that_did_not_fit_the_prompt_is_not_cited(monkeypatch):
    prompts = []
    monkeypatch.setattr(
        llm_service,
        "generate",
        lambda system, user, model=None: prompts.append(user) or llm_service.LLMResult(ok=True, text="ok"),
    )
    # Three chunks that each take most of the room: only the first can be sent.
    room = user_prompt_char_budget(SYSTEM_PROMPT, OLLAMA_MAX_OUTPUT_TOKENS)
    big = "x" * int(room * 0.7)
    retrieved = [
        {"source": f"{name}.pdf", "page": n, "text": f"{name} " + big, "similarity": 0.9 - n * 0.1}
        for n, name in enumerate(["One", "Two", "Three"], start=1)
    ]
    result = generate_tutor_answer("Q?", retrieved, "T", 50, [])

    assert result.grounded is True
    assert "One " in prompts[0] and "Three " not in prompts[0]
    cited = {s["source"] for s in result.sources}
    assert "One.pdf" in cited and "Three.pdf" not in cited
    assert len(prompts[0]) <= room


def test_the_prompt_sent_to_the_model_fits_the_budget_with_a_huge_question_and_history(monkeypatch):
    prompts = []
    monkeypatch.setattr(
        llm_service,
        "generate",
        lambda system, user, model=None: prompts.append((system, user)) or llm_service.LLMResult(ok=True, text="ok"),
    )
    retrieved = [
        {"source": "A.pdf", "page": 1, "text": "chunk text " * 100, "similarity": 0.9},
        {"source": "B.pdf", "page": 2, "text": "chunk text " * 100, "similarity": 0.8},
    ]
    history = [{"role": "user" if i % 2 == 0 else "assistant", "text": "earlier " * 500} for i in range(6)]
    generate_tutor_answer(
        "very long question " * 2000,
        retrieved,
        "T" * 255,
        50,
        [{"name": f"Prerequisite {i} " * 20, "score": 10} for i in range(30)],
        history=history,
    )

    system, user = prompts[0]
    window_tokens = prompt_token_budget(OLLAMA_MAX_OUTPUT_TOKENS)
    assert estimate_tokens(system) + estimate_tokens(user) <= window_tokens
    # The grounding rules are in the system prompt, which is never trimmed.
    assert system == SYSTEM_PROMPT


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


# --- prepare / stream ---------------------------------------------------------------------------

from app.services.tutor_service import (  # noqa: E402
    ANSWER_INTERRUPTED_NOTE,
    prepare_tutor_answer,
    stream_tutor_answer,
)

STRONG = [{"source": "A.pdf", "page": 4, "text": "Relevant text.", "similarity": 0.9}]


def test_prepare_returns_the_prompt_and_citations_without_calling_the_model(monkeypatch):
    monkeypatch.setattr(
        llm_service, "generate", lambda *a, **k: (_ for _ in ()).throw(AssertionError("no model call"))
    )
    prepared = prepare_tutor_answer("Q?", STRONG, "T", 50, [])
    assert prepared.immediate is None
    assert prepared.sources == [{"source": "A.pdf", "page": 4}]
    assert prepared.system_prompt == SYSTEM_PROMPT and "Relevant text." in prepared.user_prompt


def test_prepare_for_an_unanswerable_question_is_already_final():
    prepared = prepare_tutor_answer("Q?", [{**STRONG[0], "similarity": 0.01}], "T", 50, [])
    assert prepared.immediate is not None and prepared.immediate.grounded is False


def test_stream_with_nothing_to_ask_the_model_ends_immediately(monkeypatch):
    monkeypatch.setattr(llm_service, "generate_stream", lambda *a, **k: (_ for _ in ()).throw(AssertionError))
    prepared = prepare_tutor_answer("Q?", [], "T", 50, [])
    events = list(stream_tutor_answer(prepared))
    assert [kind for kind, _ in events] == ["end"] and events[0][1].grounded is False


def _fake_stream(monkeypatch, pieces, result):
    def fake(system, user, model=None, **kwargs):
        for piece in pieces:
            yield "token", piece
        yield "end", result

    monkeypatch.setattr(llm_service, "generate_stream", fake)


def test_stream_yields_tokens_then_the_cited_answer(monkeypatch):
    _fake_stream(monkeypatch, ["Hi ", "there"], llm_service.LLMResult(ok=True, text="Hi there"))
    events = list(stream_tutor_answer(prepare_tutor_answer("Q?", STRONG, "T", 50, [])))
    assert [e for e in events[:-1]] == [("token", "Hi "), ("token", "there")]
    kind, answer = events[-1]
    assert kind == "end" and answer.answer == "Hi there" and answer.grounded
    assert answer.sources == [{"source": "A.pdf", "page": 4}]


def test_stream_that_fails_before_any_text_is_the_unavailable_message(monkeypatch):
    _fake_stream(monkeypatch, [], llm_service.LLMResult(ok=False, error="Ollama is not running or unreachable."))
    (kind, answer), = list(stream_tutor_answer(prepare_tutor_answer("Q?", STRONG, "T", 50, [])))
    assert kind == "end" and answer.grounded is False and answer.sources == []
    assert "Ollama is not running" in answer.answer


def test_stream_that_breaks_part_way_keeps_the_text_and_notes_the_interruption(monkeypatch):
    _fake_stream(monkeypatch, ["Part"], llm_service.LLMResult(ok=False, text="Part", error="timed out"))
    *_, (kind, answer) = list(stream_tutor_answer(prepare_tutor_answer("Q?", STRONG, "T", 50, [])))
    assert answer.answer == "Part" + ANSWER_INTERRUPTED_NOTE.format(detail="timed out")
    assert answer.grounded is True and answer.sources == [{"source": "A.pdf", "page": 4}]
