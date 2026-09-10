"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-08-22

"""
from alembic import op
import sqlalchemy as sa

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    source_type = sa.Enum(
        "official_upload", "self_supplied", "web_fallback", name="source_type"
    )
    mastery_status = sa.Enum(
        "unmastered", "in_progress", "mastered", "missed", name="mastery_status"
    )
    session_type = sa.Enum("quiz", "self_report", "chat", name="session_type")

    bind = op.get_bind()
    source_type.create(bind, checkfirst=True)
    mastery_status.create(bind, checkfirst=True)
    session_type.create(bind, checkfirst=True)

    op.create_table(
        "topics",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("course", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "prerequisites",
        sa.Column(
            "topic_id",
            sa.Integer,
            sa.ForeignKey("topics.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "prerequisite_topic_id",
            sa.Integer,
            sa.ForeignKey("topics.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )

    op.create_table(
        "sources",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "topic_id", sa.Integer, sa.ForeignKey("topics.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("source_type", source_type, nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("raw_text", sa.Text, nullable=True),
        sa.Column("file_path", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "chunks",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "source_id", sa.Integer, sa.ForeignKey("sources.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "topic_id", sa.Integer, sa.ForeignKey("topics.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("chunk_text", sa.Text, nullable=False),
        sa.Column("chunk_index", sa.Integer, nullable=False),
        sa.Column("embedding", sa.JSON, nullable=True),
    )

    op.create_table(
        "mastery",
        sa.Column(
            "topic_id",
            sa.Integer,
            sa.ForeignKey("topics.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("score", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_updated", sa.DateTime, server_default=sa.func.now()),
        sa.Column("status", mastery_status, nullable=False, server_default="unmastered"),
    )

    op.create_table(
        "sessions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "topic_id", sa.Integer, sa.ForeignKey("topics.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("type", session_type, nullable=False),
        sa.Column("score_delta", sa.Integer, nullable=False, server_default="0"),
        sa.Column("timestamp", sa.DateTime, server_default=sa.func.now()),
    )

    op.create_table(
        "quiz_questions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "topic_id", sa.Integer, sa.ForeignKey("topics.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("question_text", sa.Text, nullable=False),
        sa.Column("options", sa.JSON, nullable=False),
        sa.Column("correct_option", sa.String(10), nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )


def downgrade():
    op.drop_table("quiz_questions")
    op.drop_table("sessions")
    op.drop_table("mastery")
    op.drop_table("chunks")
    op.drop_table("sources")
    op.drop_table("prerequisites")
    op.drop_table("topics")

    bind = op.get_bind()
    sa.Enum(name="session_type").drop(bind, checkfirst=True)
    sa.Enum(name="mastery_status").drop(bind, checkfirst=True)
    sa.Enum(name="source_type").drop(bind, checkfirst=True)
