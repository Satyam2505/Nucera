"""add users table and topic ownership

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-16

Backfills any pre-existing topics (from before auth existed) onto a
placeholder account so they don't become invisible/orphaned:
  email: legacy@edupilot.local
  password: changeme123
Log in with that account once to see old data, then create your own
account and re-create topics there if you want a clean separation.
"""
from alembic import op
import sqlalchemy as sa

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

# Pre-hashed with passlib's bcrypt scheme for "changeme123" — computed
# ahead of time so this migration doesn't need app code as a dependency.
_LEGACY_PASSWORD_HASH = "$2b$12$lQsfXOGeuMHIsngnBeQroOwCtsT0aLVUDqzbo1IcLHVpR2JgmwRSO"


def upgrade():
    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("email", sa.String(255), nullable=False, unique=True, index=True),
        sa.Column("hashed_password", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=True),
    )

    with op.batch_alter_table("topics") as batch_op:
        batch_op.add_column(sa.Column("user_id", sa.Integer, nullable=True))
        batch_op.create_foreign_key(
            "fk_topics_user_id", "users", ["user_id"], ["id"], ondelete="CASCADE"
        )

    conn = op.get_bind()
    users = sa.table(
        "users",
        sa.column("id", sa.Integer),
        sa.column("email", sa.String),
        sa.column("hashed_password", sa.String),
        sa.column("created_at", sa.DateTime),
    )
    topics = sa.table("topics", sa.column("id", sa.Integer), sa.column("user_id", sa.Integer))

    existing_topics = conn.execute(sa.select(topics.c.id)).fetchall()
    if existing_topics:
        conn.execute(
            users.insert().values(
                email="legacy@edupilot.local",
                hashed_password=_LEGACY_PASSWORD_HASH,
                created_at=sa.func.now(),
            )
        )
        # sa.table()'s lightweight columns carry no primary-key metadata, so
        # inserted_primary_key isn't available here — re-fetch by the
        # unique email instead, which we just inserted.
        legacy_user_id = conn.execute(
            sa.select(users.c.id).where(users.c.email == "legacy@edupilot.local")
        ).scalar_one()
        conn.execute(topics.update().values(user_id=legacy_user_id))


def downgrade():
    with op.batch_alter_table("topics") as batch_op:
        batch_op.drop_constraint("fk_topics_user_id", type_="foreignkey")
        batch_op.drop_column("user_id")
    op.drop_table("users")
