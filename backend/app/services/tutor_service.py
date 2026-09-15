"""Grounded, adaptive tutor answer generation.

Combines two kinds of intelligence, per the project's core distinction:
1. RAG grounding — retrieved chunks from the student's own uploaded material.
2. Adaptive guidance — the prerequisite graph + mastery system.

The LLM call itself is isolated in llm_service, and prompt construction is
isolated in prompt_builder, so either can be swapped or tested independently
of this orchestration layer.
"""

from dataclasses import dataclass, field
from typing import List, Optional

from app.config import OLLAMA_MODEL, RETRIEVAL_RELEVANCE_THRESHOLD
from app.services import llm_service
from app.services.prompt_builder import (
    SYSTEM_PROMPT,
    PrerequisiteGap,
    RetrievedContext,
    build_user_prompt,
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


@dataclass
class TutorAnswer:
    answer: str
    sources: List[dict] = field(default_factory=list)
    grounded: bool = True


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


def generate_tutor_answer(
    question: str,
    retrieved_chunks: List[dict],
    topic_name: Optional[str],
    topic_mastery_score: int,
    prerequisite_gaps: List[dict],
    history: Optional[List[dict]] = None,
) -> TutorAnswer:
    """
    retrieved_chunks: ranked list (best first) of
        {"source": str, "page": Optional[int], "text": str, "similarity": float}
    prerequisite_gaps: list of {"name": str, "score": int}
    history: optional list of {"role": "user"|"assistant", "text": str},
        oldest first — only the last few turns are used.
    """
    # Avoid false confidence: don't call the LLM at all when the best match
    # isn't actually relevant.
    if not retrieved_chunks or retrieved_chunks[0]["similarity"] < RETRIEVAL_RELEVANCE_THRESHOLD:
        return TutorAnswer(answer=INSUFFICIENT_MATERIAL_MESSAGE, sources=[], grounded=False)

    depth = explanation_depth_for_score(topic_mastery_score)

    context_chunks = [
        RetrievedContext(source=c["source"], page=c.get("page"), text=c["text"])
        for c in retrieved_chunks
    ]
    gaps = [PrerequisiteGap(name=g["name"], score=g["score"]) for g in prerequisite_gaps]

    user_prompt = build_user_prompt(
        question=question,
        topic_name=topic_name,
        depth=depth,
        chunks=context_chunks,
        gaps=gaps,
        history=history,
    )

    result = llm_service.generate(SYSTEM_PROMPT, user_prompt, model=OLLAMA_MODEL)

    if not result.ok:
        return TutorAnswer(
            answer=LLM_UNAVAILABLE_MESSAGE.format(detail=result.error),
            sources=[],
            grounded=False,
        )

    # Citations are built from the retrieved chunks themselves, never from
    # whatever the model happened to say — so a citation can't be fabricated.
    sources = [{"source": c["source"], "page": c.get("page")} for c in retrieved_chunks]

    return TutorAnswer(answer=result.text, sources=sources, grounded=True)
