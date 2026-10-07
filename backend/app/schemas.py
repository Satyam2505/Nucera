from datetime import datetime
from typing import Annotated, List, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints, field_validator

from app.models import MasteryStatus, SessionType, SourceType


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    email: str
    created_at: datetime


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


# Names are trimmed and must be non-empty, so "   " can't become a course,
# module or topic.
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]


class CourseCreate(BaseModel):
    name: Name
    description: Optional[str] = None


class CourseUpdate(BaseModel):
    name: Optional[Name] = None
    description: Optional[str] = None


class CourseOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    description: Optional[str] = None
    created_at: datetime
    module_count: int = 0
    topic_count: int = 0
    avg_score: int = 0


class ModuleCreate(BaseModel):
    name: Name
    description: Optional[str] = None


class ModuleUpdate(BaseModel):
    name: Optional[Name] = None
    description: Optional[str] = None
    # Move the module to this 0-based index among its siblings.
    position: Optional[int] = Field(default=None, ge=0)


class OrderUpdate(BaseModel):
    ids: List[int]


class TreeTopic(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    position: int
    status: MasteryStatus
    score: int
    flagged_for_revision: bool


class TreeModule(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    position: int
    topics: List[TreeTopic]


class CourseTree(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    created_at: datetime
    modules: List[TreeModule]


class TopicCreate(BaseModel):
    name: Name
    module_id: int
    description: Optional[str] = None


class TopicUpdate(BaseModel):
    name: Optional[Name] = None
    description: Optional[str] = None
    # Moving to a module of the same course; appended at the end of it.
    module_id: Optional[int] = None


class TopicOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    description: Optional[str] = None
    created_at: datetime
    module_id: int
    position: int
    module_name: str
    course_id: int
    course_name: str


class PrerequisiteCreate(BaseModel):
    topic_id: int
    prerequisite_topic_id: int


class SourceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    topic_id: int
    source_type: SourceType
    title: str
    created_at: datetime
    chunk_count: int


class IngestTextRequest(BaseModel):
    topic_id: int
    source_type: SourceType
    # Trimmed, non-empty, and no longer than the column.
    title: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
    # Blank (or whitespace-only) text is a 422, not an empty source.
    text: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class MasteryOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    topic_id: int
    score: int
    last_updated: datetime
    status: MasteryStatus
    flagged_for_revision: bool


class MasteryUpdate(BaseModel):
    # Only the score can be set; the status is derived from it. Unknown fields
    # (such as the old `status`) are rejected rather than silently ignored.
    model_config = ConfigDict(extra="forbid")
    score: Optional[int] = None


class SessionCreate(BaseModel):
    topic_id: int
    type: SessionType
    score_delta: int = 0


class SessionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    topic_id: int
    type: SessionType
    score_delta: int
    timestamp: datetime


class SessionHistoryItem(BaseModel):
    """One entry of the study-session timeline."""

    id: int
    topic_id: int
    topic_name: str
    type: SessionType
    score_delta: int
    timestamp: Optional[datetime] = None


class SourceCitation(BaseModel):
    source: str
    page: Optional[int] = None
    # Set only when the passage came from another topic of the same course (the
    # tutor widens its search when the topic's own material has nothing relevant).
    topic: Optional[str] = None


class QuizQuestionOut(BaseModel):
    """A question as shown before it is graded: no key, no explanation."""

    model_config = ConfigDict(from_attributes=True)
    id: int
    position: int
    question_text: str
    options: dict


class QuizAnswer(BaseModel):
    question_id: int
    selected_option: str


class QuizSubmitRequest(BaseModel):
    quiz_set_id: int
    answers: List[QuizAnswer]


class QuizResultItem(BaseModel):
    question_id: int
    question_text: str
    options: dict
    chosen: Optional[str] = None
    correct_option: str
    is_correct: bool
    explanation: Optional[str] = None
    sources: List[SourceCitation] = []


class QuizAttemptOut(BaseModel):
    id: int
    quiz_set_id: int
    correct: int
    total: int
    score_percent: float
    score_delta: int
    created_at: datetime
    results: List[QuizResultItem]
    # The topic's mastery as it stands now (after this attempt, if it is the latest).
    mastery: Optional[MasteryOut] = None


class QuizSetOut(BaseModel):
    id: int
    topic_id: int
    created_at: datetime
    questions: List[QuizQuestionOut]
    # Present once the set has been graded; answers and explanations are only
    # ever sent as part of it.
    attempt: Optional[QuizAttemptOut] = None


class QuizJobOut(BaseModel):
    """Progress of a background quiz generation. Carries no questions or answers:
    the finished quiz is read the usual way, so nothing is ever sent ungraded
    that wasn't before."""

    model_config = ConfigDict(from_attributes=True)
    id: int
    topic_id: int
    # queued | running | succeeded | partial | failed
    status: str
    requested: int
    completed: int
    error: Optional[str] = None
    created_at: Optional[datetime] = None
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


class QuizState(BaseModel):
    # The latest quiz that can be taken (never one still being written).
    quiz_set: Optional[QuizSetOut] = None
    # Whether the topic has any study material to generate a quiz from.
    has_material: bool
    # The topic's queued or running generation, if any, so a reload resumes its progress.
    job: Optional[QuizJobOut] = None


class QuizSummary(BaseModel):
    """One past quiz in a topic's list: enough to pick one, no questions."""

    id: int
    created_at: Optional[datetime] = None
    question_count: int
    taken: bool
    correct: Optional[int] = None
    total: Optional[int] = None
    score_percent: Optional[float] = None
    attempted_at: Optional[datetime] = None


class AskRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000)
    topic_id: int

    @field_validator("query")
    @classmethod
    def _query_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Ask a question.")
        return value.strip()


class AskResponse(BaseModel):
    answer: str
    flagged_prerequisites: List[TopicOut]
    sources: List[SourceCitation] = []
    # False when the answer is a fallback (insufficient material, or the
    # local model was unavailable) rather than a real grounded response.
    grounded: bool = True


class RetrieveRequest(BaseModel):
    question: str
    topic_id: Optional[int] = None
    source_ids: Optional[List[int]] = None
    top_k: int = 5


class RetrievedChunk(BaseModel):
    chunk_id: int
    source_id: int
    filename: str
    page_number: Optional[int] = None
    chunk_index: int
    similarity_score: float
    # Contains every searchable word of the question (see retrieval_service).
    keyword_match: bool = False
    chunk_text: str


class RetrieveResponse(BaseModel):
    question: str
    results: List[RetrievedChunk]


class ChatMessageOut(BaseModel):
    """One saved turn of a topic's tutor conversation."""

    model_config = ConfigDict(from_attributes=True)
    id: int
    role: str
    content: str
    sources: List[SourceCitation] = []
    flagged: List[str] = []
    grounded: Optional[bool] = None
    created_at: datetime

    @field_validator("sources", "flagged", mode="before")
    @classmethod
    def _none_is_empty(cls, value):
        return [] if value is None else value
