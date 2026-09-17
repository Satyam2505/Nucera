import enum
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import relationship

from app.database import Base


class SourceType(str, enum.Enum):
    official_upload = "official_upload"
    self_supplied = "self_supplied"
    web_fallback = "web_fallback"


class MasteryStatus(str, enum.Enum):
    unmastered = "unmastered"
    in_progress = "in_progress"
    mastered = "mastered"
    missed = "missed"


class SessionType(str, enum.Enum):
    quiz = "quiz"
    self_report = "self_report"
    chat = "chat"


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    email = Column(String(255), unique=True, nullable=False, index=True)
    hashed_password = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    topics = relationship("Topic", back_populates="owner")


class Topic(Base):
    __tablename__ = "topics"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    name = Column(String(255), nullable=False)
    course = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    owner = relationship("User", back_populates="topics")

    mastery = relationship(
        "Mastery", back_populates="topic", uselist=False, cascade="all, delete-orphan"
    )
    sources = relationship("Source", back_populates="topic", cascade="all, delete-orphan")
    chunks = relationship("Chunk", back_populates="topic", cascade="all, delete-orphan")
    sessions = relationship(
        "StudySession", back_populates="topic", cascade="all, delete-orphan"
    )
    quiz_questions = relationship(
        "QuizQuestion", back_populates="topic", cascade="all, delete-orphan"
    )

    prerequisites = relationship(
        "Prerequisite",
        foreign_keys="Prerequisite.topic_id",
        back_populates="topic",
        cascade="all, delete-orphan",
    )
    dependents = relationship(
        "Prerequisite",
        foreign_keys="Prerequisite.prerequisite_topic_id",
        back_populates="prerequisite_topic",
        cascade="all, delete-orphan",
    )


class Prerequisite(Base):
    __tablename__ = "prerequisites"

    topic_id = Column(
        Integer, ForeignKey("topics.id", ondelete="CASCADE"), primary_key=True
    )
    prerequisite_topic_id = Column(
        Integer, ForeignKey("topics.id", ondelete="CASCADE"), primary_key=True
    )

    topic = relationship(
        "Topic", foreign_keys=[topic_id], back_populates="prerequisites"
    )
    prerequisite_topic = relationship(
        "Topic", foreign_keys=[prerequisite_topic_id], back_populates="dependents"
    )


class Source(Base):
    __tablename__ = "sources"

    id = Column(Integer, primary_key=True)
    topic_id = Column(Integer, ForeignKey("topics.id", ondelete="CASCADE"), nullable=False)
    source_type = Column(SQLEnum(SourceType, name="source_type"), nullable=False)
    title = Column(String(255), nullable=False)
    raw_text = Column(Text, nullable=True)
    file_path = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    topic = relationship("Topic", back_populates="sources")
    chunks = relationship("Chunk", back_populates="source", cascade="all, delete-orphan")

    @property
    def chunk_count(self) -> int:
        return len(self.chunks)


class Chunk(Base):
    __tablename__ = "chunks"

    id = Column(Integer, primary_key=True)
    source_id = Column(Integer, ForeignKey("sources.id", ondelete="CASCADE"), nullable=False)
    topic_id = Column(Integer, ForeignKey("topics.id", ondelete="CASCADE"), nullable=False)
    chunk_text = Column(Text, nullable=False)
    chunk_index = Column(Integer, nullable=False)
    # Page the chunk came from (1-indexed). Null for plain-text sources,
    # which have no page structure.
    page_number = Column(Integer, nullable=True)
    embedding = Column(JSON, nullable=True)

    source = relationship("Source", back_populates="chunks")
    topic = relationship("Topic", back_populates="chunks")


class Mastery(Base):
    __tablename__ = "mastery"

    topic_id = Column(
        Integer, ForeignKey("topics.id", ondelete="CASCADE"), primary_key=True
    )
    score = Column(Integer, default=0, nullable=False)
    last_updated = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    flagged_for_revision = Column(Boolean, default=False, nullable=False)
    status = Column(
        SQLEnum(MasteryStatus, name="mastery_status"),
        default=MasteryStatus.unmastered,
        nullable=False,
    )

    topic = relationship("Topic", back_populates="mastery")


class StudySession(Base):
    __tablename__ = "sessions"

    id = Column(Integer, primary_key=True)
    topic_id = Column(Integer, ForeignKey("topics.id", ondelete="CASCADE"), nullable=False)
    type = Column(SQLEnum(SessionType, name="session_type"), nullable=False)
    score_delta = Column(Integer, default=0, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow)

    topic = relationship("Topic", back_populates="sessions")


class QuizQuestion(Base):
    __tablename__ = "quiz_questions"

    id = Column(Integer, primary_key=True)
    topic_id = Column(Integer, ForeignKey("topics.id", ondelete="CASCADE"), nullable=False)
    question_text = Column(Text, nullable=False)
    options = Column(JSON, nullable=False)
    correct_option = Column(String(10), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    topic = relationship("Topic", back_populates="quiz_questions")
