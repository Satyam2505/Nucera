"""add shared_with_module to sources

A source shared with its module is used by every topic in its topic's module.

Revision ID: 0012
Revises: 0011
Create Date: 2026-10-27

"""
from alembic import op
import sqlalchemy as sa

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "sources",
        sa.Column("shared_with_module", sa.Boolean, nullable=False, server_default=sa.false()),
    )


def downgrade():
    op.drop_column("sources", "shared_with_module")
