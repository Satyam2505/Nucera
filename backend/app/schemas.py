from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict

from app.models import MasteryStatus, SessionType, SourceType


class TopicBase(BaseModel):
    name: str
    course: str
    description: Optional[str] = None


class TopicCreate(TopicBase):
    pass


class TopicOut(TopicBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: datetime


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


class MasteryUpdate(BaseModel):
    score: Optional[int] = None
    status: Optional[MasteryStatus] = None


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


class QuizQuestionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    topic_id: int
    question_text: str
    options: dict


class QuizAnswer(BaseModel):
    question_id: int
    selected_option: str


class QuizSubmitRequest(BaseModel):
    topic_id: int
    answers: List[QuizAnswer]


class QuizSubmitResult(BaseModel):
    total: int
    correct: int
    score_percent: float
    mastery: MasteryOut


class AskRequest(BaseModel):
    query: str
    topic_id: int


class AskResponse(BaseModel):
    answer: str
    flagged_prerequisites: List[TopicOut]


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
