"""chat messages: the tutor conversation is kept per topic on the server

Revision ID: 0007
Revises: 0006
Create Date: 2026-10-07

Chat history used to live only in the browser, so a reload or a switch to
another topic lost it. Each turn is now a row in chat_messages, owned through
its topic (deleted with it). Nothing existing is changed or backfilled: the
old conversations were never stored, so every topic starts with an empty chat.

Written with plain table definitions, not app.models, so it keeps working
after the models change. Downgrade drops the table (and with it the saved
conversations).
"""
from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "chat_messages",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "topic_id",
            sa.Integer,
            sa.ForeignKey("topics.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("content", sa.Text, nullable=False),
        sa.Column("sources", sa.JSON, nullable=True),
        sa.Column("flagged", sa.JSON, nullable=True),
        sa.Column("grounded", sa.Boolean, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )


def downgrade():
    op.drop_table("chat_messages")
