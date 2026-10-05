"""quiz sets and attempts; quiz questions move under a set

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-06

Quizzes were three hardcoded "[stub] ... Placeholder A" questions per topic,
cached forever. Real generation now writes one quiz_sets row per generation
(so regenerating keeps history), quiz_questions hang off a set instead of a
topic (topic_id is dropped; the topic is reached through the set), and
quiz_attempts record each graded submission.

Existing quiz_questions rows are DELETED, not carried over: every one of them
is a stub with a fixed answer key, so showing them as the "latest set" would
grade placeholders as if they were real questions. This also removes any
orphaned rows whose topic no longer exists. Mastery history is untouched (the
quiz study sessions and score deltas stay in `sessions`).

Written with lightweight table definitions rather than app.models so it keeps
working after the models change. Downgrade restores quiz_questions.topic_id
from each question's set, then drops the new tables.
"""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

_quiz_questions = sa.table("quiz_questions", sa.column("id", sa.Integer))
_quiz_questions_with_topic = sa.table(
    "quiz_questions", sa.column("id", sa.Integer), sa.column("topic_id", sa.Integer)
)
_quiz_questions_with_set = sa.table(
    "quiz_questions", sa.column("id", sa.Integer), sa.column("quiz_set_id", sa.Integer)
)
_quiz_sets = sa.table("quiz_sets", sa.column("id", sa.Integer), sa.column("topic_id", sa.Integer))


def upgrade():
    # Stub questions (and orphans) go first, so quiz_set_id can be NOT NULL
    # without inventing a set for them.
    op.get_bind().execute(_quiz_questions.delete())

    op.create_table(
        "quiz_sets",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "topic_id",
            sa.Integer,
            sa.ForeignKey("topics.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )
    op.create_table(
        "quiz_attempts",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "quiz_set_id",
            sa.Integer,
            sa.ForeignKey("quiz_sets.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("correct", sa.Integer, nullable=False),
        sa.Column("total", sa.Integer, nullable=False),
        sa.Column("score_percent", sa.Float, nullable=False),
        sa.Column("score_delta", sa.Integer, nullable=False),
        sa.Column("answers", sa.JSON, nullable=False),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    with op.batch_alter_table("quiz_questions") as batch_op:
        batch_op.add_column(sa.Column("quiz_set_id", sa.Integer, nullable=False))
        batch_op.add_column(
            sa.Column("position", sa.Integer, nullable=False, server_default="0")
        )
        batch_op.add_column(sa.Column("explanation", sa.Text, nullable=True))
        batch_op.add_column(sa.Column("sources", sa.JSON, nullable=True))
        batch_op.create_foreign_key(
            "fk_quiz_questions_quiz_set_id", "quiz_sets", ["quiz_set_id"], ["id"], ondelete="CASCADE"
        )
        batch_op.create_index("ix_quiz_questions_quiz_set_id", ["quiz_set_id"])
        batch_op.drop_column("topic_id")


def downgrade():
    with op.batch_alter_table("quiz_questions") as batch_op:
        batch_op.add_column(sa.Column("topic_id", sa.Integer, nullable=True))

    conn = op.get_bind()
    rows = conn.execute(
        sa.select(_quiz_questions_with_set.c.id, _quiz_sets.c.topic_id).select_from(
            _quiz_questions_with_set.join(
                _quiz_sets, _quiz_sets.c.id == _quiz_questions_with_set.c.quiz_set_id
            )
        )
    ).fetchall()
    for question_id, topic_id in rows:
        conn.execute(
            _quiz_questions_with_topic.update()
            .where(_quiz_questions_with_topic.c.id == question_id)
            .values(topic_id=topic_id)
        )

    with op.batch_alter_table("quiz_questions") as batch_op:
        batch_op.alter_column("topic_id", existing_type=sa.Integer, nullable=False)
        batch_op.create_foreign_key(
            "fk_quiz_questions_topic_id", "topics", ["topic_id"], ["id"], ondelete="CASCADE"
        )
        batch_op.drop_constraint("fk_quiz_questions_quiz_set_id", type_="foreignkey")
        batch_op.drop_index("ix_quiz_questions_quiz_set_id")
        batch_op.drop_column("quiz_set_id")
        batch_op.drop_column("position")
        batch_op.drop_column("explanation")
        batch_op.drop_column("sources")

    op.drop_table("quiz_attempts")
    op.drop_table("quiz_sets")
