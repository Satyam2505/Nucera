"""Grounded, adaptive tutor answer generation.

Combines two kinds of intelligence, per the project's core distinction:
1. RAG grounding — retrieved chunks from the student's own uploaded material.
2. Adaptive guidance — the prerequisite graph + mastery system.

The LLM call itself is isolated in llm_service, and prompt construction is
isolated in prompt_builder, so either can be swapped or tested independently
of this orchestration layer.

An answer is produced in two steps so the same logic serves a blocking reply
and a streamed one: prepare_tutor_answer() decides whether the model is needed
at all and builds the prompt and the citations; generate_tutor_answer() or
stream_tutor_answer() then run the model.
"""

from dataclasses import dataclass, field
from typing import Iterator, List, Optional, Tuple, Union

from app.config import OLLAMA_MAX_OUTPUT_TOKENS, OLLAMA_MODEL, RETRIEVAL_RELEVANCE_THRESHOLD
from app.services import llm_service
from app.services.context_budget import user_prompt_char_budget
from app.services.prompt_builder import (
    SYSTEM_PROMPT,
    PrerequisiteGap,
    RetrievedContext,
    build_budgeted_prompt,
)

INSUFFICIENT_MATERIAL_MESSAGE = (
    "I couldn't find enough information about this in your uploaded study "
    "material. Try uploading notes that cover this topic, or ask about "
    "something already in your sources."
)

LLM_UNAVAILABLE_MESSAGE = (
    "I found relevant material, but the local tutor model isn't available "
    "right now, so I can't generate an explanation. ({detail})"
)

# Appended to an answer that stopped part-way because the model connection broke.
ANSWER_INTERRUPTED_NOTE = "\n\n*(The answer was cut short: {detail})*"


@dataclass
class TutorAnswer:
    answer: str
    sources: List[dict] = field(default_factory=list)
    grounded: bool = True


@dataclass
class PreparedAnswer:
    """Either a finished answer that needs no model (`immediate`), or the
    prompt to send and the citations that go with it."""

    immediate: Optional[TutorAnswer] = None
    system_prompt: str = ""
    user_prompt: str = ""
    sources: List[dict] = field(default_factory=list)


def explanation_depth_for_score(score: int) -> str:
    """Deterministic, explicit mapping from mastery score to explanation
    depth. Kept simple and in code — the model is told which depth to use
    rather than left to infer it from a raw number.
    """
    if score >= 80:
        return "high"
    if score >= 40:
        return "medium"
    return "low"


def prepare_tutor_answer(
    question: str,
    retrieved_chunks: List[dict],
    topic_name: Optional[str],
    topic_mastery_score: int,
    prerequisite_gaps: List[dict],
    history: Optional[List[dict]] = None,
) -> PreparedAnswer:
    """
    retrieved_chunks: ranked list (best first) of
        {"source": str, "page": Optional[int], "text": str, "similarity": float}
    prerequisite_gaps: list of {"name": str, "score": int}
    history: optional list of {"role": "user"|"assistant", "text": str},
        oldest first — only the last few turns are used.
    """
    # Avoid false confidence: only chunks that clear the relevance threshold
    # are used at all. If none do, the LLM is not called. Weaker chunks that
    # merely came back in the top few are neither shown to the model (they
    # would only invite it to build on irrelevant text) nor cited.
    relevant = sorted(
        (c for c in retrieved_chunks if c["similarity"] >= RETRIEVAL_RELEVANCE_THRESHOLD),
        key=lambda c: c["similarity"],
        reverse=True,
    )
    if not relevant:
        return PreparedAnswer(
            immediate=TutorAnswer(answer=INSUFFICIENT_MATERIAL_MESSAGE, sources=[], grounded=False)
        )

    depth = explanation_depth_for_score(topic_mastery_score)

    context_chunks = [
        RetrievedContext(source=c["source"], page=c.get("page"), text=c["text"])
        for c in relevant
    ]
    gaps = [PrerequisiteGap(name=g["name"], score=g["score"]) for g in prerequisite_gaps]

    # The prompt is sized to the model's context window so the system prompt's
    # grounding rules are never the part that gets cut off.
    built = build_budgeted_prompt(
        question=question,
        topic_name=topic_name,
        depth=depth,
        chunks=context_chunks,
        gaps=gaps,
        history=history,
        max_chars=user_prompt_char_budget(SYSTEM_PROMPT, OLLAMA_MAX_OUTPUT_TOKENS),
    )

    # Citations are built from the chunks the model will actually be shown,
    # never from whatever the model happens to say — so a citation can't be
    # fabricated, and a chunk dropped for lack of room isn't cited.
    sources = [
        {"source": relevant[i]["source"], "page": relevant[i].get("page")}
        for i in built.chunks_used
    ]
    return PreparedAnswer(system_prompt=SYSTEM_PROMPT, user_prompt=built.text, sources=sources)


def _unavailable(detail: Optional[str]) -> TutorAnswer:
    return TutorAnswer(
        answer=LLM_UNAVAILABLE_MESSAGE.format(detail=detail), sources=[], grounded=False
    )


def _answer_from(prepared: PreparedAnswer, result: llm_service.LLMResult) -> TutorAnswer:
    if result.ok:
        return TutorAnswer(answer=result.text, sources=prepared.sources, grounded=True)
    if result.text.strip():
        # The model had started answering when the connection broke: keep what
        # arrived (it is still grounded in the cited material) and say it stopped.
        return TutorAnswer(
            answer=result.text + ANSWER_INTERRUPTED_NOTE.format(detail=result.error),
            sources=prepared.sources,
            grounded=True,
        )
    return _unavailable(result.error)


def generate_tutor_answer(
    question: str,
    retrieved_chunks: List[dict],
    topic_name: Optional[str],
    topic_mastery_score: int,
    prerequisite_gaps: List[dict],
    history: Optional[List[dict]] = None,
) -> TutorAnswer:
    prepared = prepare_tutor_answer(
        question, retrieved_chunks, topic_name, topic_mastery_score, prerequisite_gaps, history
    )
    return answer_prepared(prepared)


def answer_prepared(prepared: PreparedAnswer) -> TutorAnswer:
    """Run the model (blocking) for an already prepared answer."""
    if prepared.immediate is not None:
        return prepared.immediate
    result = llm_service.generate(prepared.system_prompt, prepared.user_prompt, model=OLLAMA_MODEL)
    return _answer_from(prepared, result)


def stream_tutor_answer(
    prepared: PreparedAnswer,
    abort: Optional[llm_service.StreamAbort] = None,
) -> Iterator[Tuple[str, Union[str, TutorAnswer]]]:
    """Yields ("token", text) as the model writes, then exactly one
    ("end", TutorAnswer) holding the final answer, citations and grounded flag.
    When no model call is needed the only event is the "end".
    """
    if prepared.immediate is not None:
        yield "end", prepared.immediate
        return

    result: Optional[llm_service.LLMResult] = None
    for kind, value in llm_service.generate_stream(
        prepared.system_prompt, prepared.user_prompt, model=OLLAMA_MODEL, abort=abort
    ):
        if kind == "token":
            yield "token", value
        else:
            result = value
    if result is None:  # generate_stream always ends with a result; belt and braces
        result = llm_service.LLMResult(ok=False, error="The local model returned nothing.")
    yield "end", _answer_from(prepared, result)
