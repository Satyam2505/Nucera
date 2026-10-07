"""quiz jobs (background generation) and a status on quiz sets

Revision ID: 0008
Revises: 0007
Create Date: 2026-10-08

Quiz generation used to be one blocking request guarded by an in-memory set, so a
second worker or a restart could start (or lose) a generation, and a failure
after minutes of model time threw everything away. It now runs as a job:

- quiz_jobs records each run (status, how many questions are written, any error).
  A partial unique index over the active statuses ('queued', 'running') lets the
  database itself refuse a second active job for a topic.
- quiz_sets.status distinguishes a set still being filled ('generating', hidden
  from every quiz view) from one that can be taken ('ready'). Every existing set
  is complete, so they all become 'ready' (the column's server default does it).

Written with plain table definitions, not app.models. Downgrade removes the
unfinished sets and their questions (never visible), then the column, index and table.
"""
from alembic import op
import sqlalchemy as sa

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

_ACTIVE = "status IN ('queued', 'running')"
_quiz_sets = sa.table("quiz_sets", sa.column("id", sa.Integer), sa.column("status", sa.String))
_quiz_questions = sa.table("quiz_questions", sa.column("quiz_set_id", sa.Integer))


def upgrade():
    with op.batch_alter_table("quiz_sets") as batch_op:
        batch_op.add_column(
            sa.Column("status", sa.String(16), nullable=False, server_default="ready")
        )

    op.create_table(
        "quiz_jobs",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "topic_id",
            sa.Integer,
            sa.ForeignKey("topics.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "quiz_set_id",
            sa.Integer,
            sa.ForeignKey("quiz_sets.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("requested", sa.Integer, nullable=False),
        sa.Column("completed", sa.Integer, nullable=False, server_default="0"),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.Column("started_at", sa.DateTime, nullable=True),
        sa.Column("finished_at", sa.DateTime, nullable=True),
        sa.Column("heartbeat_at", sa.DateTime, nullable=True),
    )
    op.create_index(
        "uq_quiz_jobs_one_active_per_topic",
        "quiz_jobs",
        ["topic_id"],
        unique=True,
        sqlite_where=sa.text(_ACTIVE),
        postgresql_where=sa.text(_ACTIVE),
    )


def downgrade():
    op.drop_index("uq_quiz_jobs_one_active_per_topic", table_name="quiz_jobs")
    op.drop_table("quiz_jobs")

    # A set that was still being filled was never shown; drop it and its questions
    # rather than let it appear as a half-written quiz. The questions are deleted
    # explicitly: SQLite does not enforce ON DELETE CASCADE inside a migration.
    unfinished = sa.select(_quiz_sets.c.id).where(_quiz_sets.c.status == "generating")
    conn = op.get_bind()
    conn.execute(_quiz_questions.delete().where(_quiz_questions.c.quiz_set_id.in_(unfinished)))
    conn.execute(_quiz_sets.delete().where(_quiz_sets.c.status == "generating"))
    with op.batch_alter_table("quiz_sets") as batch_op:
        batch_op.drop_column("status")
