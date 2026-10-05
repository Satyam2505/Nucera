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
    UniqueConstraint,
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
    courses = relationship("Course", back_populates="owner", cascade="all, delete-orphan")


class Course(Base):
    """The top of the Course -> Module -> Topic hierarchy (the "book").

    user_id is nullable only because courses backfilled from pre-auth
    topics (and the unowned seed) have no real owner; such a course is
    invisible to every account rather than being handed to a made-up one.
    """

    __tablename__ = "courses"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_courses_user_name"),)

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    owner = relationship("User", back_populates="courses")
    modules = relationship(
        "Module",
        back_populates="course",
        cascade="all, delete-orphan",
        order_by="Module.position",
    )


class Module(Base):
    """A chapter of a course. `position` orders modules within the course."""

    __tablename__ = "modules"

    id = Column(Integer, primary_key=True)
    course_id = Column(
        Integer, ForeignKey("courses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    position = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    course = relationship("Course", back_populates="modules")
    topics = relationship(
        "Topic",
        back_populates="module",
        cascade="all, delete-orphan",
        order_by="Topic.position",
    )


class Topic(Base):
    __tablename__ = "topics"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    module_id = Column(
        Integer, ForeignKey("modules.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    # Order within the module (0-based, kept contiguous by the API).
    position = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)

    owner = relationship("User", back_populates="topics")
    module = relationship("Module", back_populates="topics")

    # Denormalised onto TopicOut so the UI can show "Course · Module" and
    # link by course id without extra fetches.
    @property
    def module_name(self) -> str:
        return self.module.name

    @property
    def course_id(self) -> int:
        return self.module.course_id

    @property
    def course_name(self) -> str:
        return self.module.course.name

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
