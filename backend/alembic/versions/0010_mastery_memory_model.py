"""mastery memory model: estimate, stability and last review time

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-09

A topic's mastery used to be one integer that never decayed. The model in
services/mastery_model.py keeps three numbers per topic: `estimate` (0-1, how well it
is known), `stability_days` (the half-life of the memory) and `last_reviewed_at`; the
score shown is estimate x what is left of the memory, so it fades without review.

Existing rows are carried over without changing what anyone sees today:
- a topic with a score above zero gets estimate = score / 100, a half-life of
  3 + 0.1 x score days (a stronger score is assumed to be a firmer memory: 3 to 13
  days) and last_reviewed_at = the time of this migration, so nothing has faded yet
  and the clock starts now (using the old `last_updated` would drop every topic that
  hasn't been touched for a while the moment the app is upgraded);
- a topic at zero has no history: estimate 0, default half-life, no last_reviewed_at.

Written with plain table definitions, not app.models. Downgrade drops the three columns
(the stored `score` and `status` are untouched, so each topic keeps the score it had at
its last review).
"""
from alembic import op
import sqlalchemy as sa

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

_mastery = sa.table(
    "mastery",
    sa.column("topic_id", sa.Integer),
    sa.column("score", sa.Integer),
    sa.column("estimate", sa.Float),
    sa.column("stability_days", sa.Float),
    sa.column("last_reviewed_at", sa.DateTime),
)


def upgrade():
    with op.batch_alter_table("mastery") as batch_op:
        batch_op.add_column(sa.Column("estimate", sa.Float, nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("stability_days", sa.Float, nullable=False, server_default="3"))
        batch_op.add_column(sa.Column("last_reviewed_at", sa.DateTime, nullable=True))

    conn = op.get_bind()
    conn.execute(
        _mastery.update()
        .where(_mastery.c.score > 0)
        .values(
            estimate=_mastery.c.score / 100.0,
            stability_days=3.0 + _mastery.c.score * 0.1,
            last_reviewed_at=sa.func.current_timestamp(),
        )
    )


def downgrade():
    with op.batch_alter_table("mastery") as batch_op:
        batch_op.drop_column("last_reviewed_at")
        batch_op.drop_column("stability_days")
        batch_op.drop_column("estimate")
