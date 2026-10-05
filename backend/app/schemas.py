from datetime import datetime
from typing import Annotated, List, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, StringConstraints

from app.models import MasteryStatus, SessionType, SourceType


class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)


class UserLogin(BaseModel):
    email: EmailStr
    password: str


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


class ChunkOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    source_id: int
    topic_id: int
    chunk_text: str
    chunk_index: int
    page_number: Optional[int] = None


class IngestTextRequest(BaseModel):
    topic_id: int
    source_type: SourceType
    title: str
    text: str


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


class SourceCitation(BaseModel):
    source: str
    page: Optional[int] = None


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


class QuizState(BaseModel):
    quiz_set: Optional[QuizSetOut] = None
    # Whether the topic has any study material to generate a quiz from.
    has_material: bool


class ChatTurn(BaseModel):
    role: str  # "user" | "assistant"
    text: str


class AskRequest(BaseModel):
    query: str
    topic_id: int
    # Short, client-held conversation history (the frontend already keeps
    # this in memory) — only the most recent few turns are used server-side.
    # Not persisted; see known limitations re: the sessions table.
    history: Optional[List[ChatTurn]] = None


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
    chunk_text: str


class RetrieveResponse(BaseModel):
    question: str
    results: List[RetrievedChunk]
