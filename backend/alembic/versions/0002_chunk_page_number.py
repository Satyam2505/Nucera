"""add page_number to chunks

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-15

"""
from alembic import op
import sqlalchemy as sa

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("chunks", sa.Column("page_number", sa.Integer, nullable=True))


def downgrade():
    op.drop_column("chunks", "page_number")
