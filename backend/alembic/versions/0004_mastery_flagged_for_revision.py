"""add flagged_for_revision to mastery

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-17

"""
from alembic import op
import sqlalchemy as sa

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "mastery",
        sa.Column("flagged_for_revision", sa.Boolean, nullable=False, server_default=sa.false()),
    )


def downgrade():
    op.drop_column("mastery", "flagged_for_revision")
