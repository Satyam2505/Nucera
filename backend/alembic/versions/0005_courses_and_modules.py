"""add courses and modules, replace topics.course with topics.module_id

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-06

Course -> Module -> Topic. Until now a "course" was only the string in
topics.course. Backfill, per distinct (user_id, course) pair found in
topics: one course, one module named "General" at position 0, and every
topic of that pair pointed at the module (positions in topic id order).

Topics with a NULL user_id (the unowned seed data) become courses with a
NULL owner — no owner is invented for them, so they stay invisible to
every account exactly as the topics were.

Written with lightweight table definitions rather than app.models so it
keeps working after the models change. Downgrade restores topics.course
from the course name; module structure (and any course with several
modules collapsing to one name) is lost by design.
"""
from alembic import op
import sqlalchemy as sa

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

DEFAULT_MODULE_NAME = "General"

# Batch mode recreates `topics` on SQLite, so the read-side and write-side
# views of the table are declared separately and only ever used at the
# point where those columns exist.
_courses = sa.table(
    "courses",
    sa.column("id", sa.Integer),
    sa.column("user_id", sa.Integer),
    sa.column("name", sa.String),
    sa.column("description", sa.Text),
    sa.column("created_at", sa.DateTime),
)
_modules = sa.table(
    "modules",
    sa.column("id", sa.Integer),
    sa.column("course_id", sa.Integer),
    sa.column("name", sa.String),
    sa.column("description", sa.Text),
    sa.column("position", sa.Integer),
    sa.column("created_at", sa.DateTime),
)
_topics_read = sa.table(
    "topics",
    sa.column("id", sa.Integer),
    sa.column("user_id", sa.Integer),
    sa.column("course", sa.String),
)
_topics_write = sa.table(
    "topics",
    sa.column("id", sa.Integer),
    sa.column("module_id", sa.Integer),
    sa.column("position", sa.Integer),
)
_topics_check = sa.table(
    "topics",
    sa.column("id", sa.Integer),
    sa.column("module_id", sa.Integer),
)


def _owner_matches(column, user_id):
    return column.is_(None) if user_id is None else column == user_id


def upgrade():
    op.create_table(
        "courses",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "user_id", sa.Integer, sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=True
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "name", name="uq_courses_user_name"),
    )
    op.create_table(
        "modules",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column(
            "course_id",
            sa.Integer,
            sa.ForeignKey("courses.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("position", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime, server_default=sa.func.now()),
    )

    with op.batch_alter_table("topics") as batch_op:
        batch_op.add_column(sa.Column("module_id", sa.Integer, nullable=True))
        batch_op.add_column(
            sa.Column("position", sa.Integer, nullable=False, server_default="0")
        )
        batch_op.create_foreign_key(
            "fk_topics_module_id", "modules", ["module_id"], ["id"], ondelete="CASCADE"
        )
        batch_op.create_index("ix_topics_module_id", ["module_id"])

    conn = op.get_bind()

    # Ordered by each pair's lowest topic id so course/module ids come out
    # the same on every run against the same data.
    pairs = conn.execute(
        sa.select(
            _topics_read.c.user_id,
            _topics_read.c.course,
            sa.func.min(_topics_read.c.id).label("first_topic_id"),
        )
        .group_by(_topics_read.c.user_id, _topics_read.c.course)
        .order_by(sa.literal_column("first_topic_id"))
    ).fetchall()

    for user_id, course_name, _first_topic_id in pairs:
        conn.execute(
            _courses.insert().values(
                user_id=user_id, name=course_name, created_at=sa.func.now()
            )
        )
        # sa.table()'s lightweight columns carry no primary-key metadata, so
        # inserted_primary_key isn't available — re-fetch by the (user, name)
        # pair, which is unique among the rows inserted here.
        course_id = conn.execute(
            sa.select(_courses.c.id).where(
                _owner_matches(_courses.c.user_id, user_id),
                _courses.c.name == course_name,
            )
        ).scalar_one()

        conn.execute(
            _modules.insert().values(
                course_id=course_id,
                name=DEFAULT_MODULE_NAME,
                position=0,
                created_at=sa.func.now(),
            )
        )
        module_id = conn.execute(
            sa.select(_modules.c.id).where(_modules.c.course_id == course_id)
        ).scalar_one()

        topic_ids = (
            conn.execute(
                sa.select(_topics_read.c.id)
                .where(
                    _owner_matches(_topics_read.c.user_id, user_id),
                    _topics_read.c.course == course_name,
                )
                .order_by(_topics_read.c.id)
            )
            .scalars()
            .all()
        )
        for position, topic_id in enumerate(topic_ids):
            conn.execute(
                _topics_write.update()
                .where(_topics_write.c.id == topic_id)
                .values(module_id=module_id, position=position)
            )

    orphans = conn.execute(
        sa.select(sa.func.count()).select_from(_topics_check).where(
            _topics_check.c.module_id.is_(None)
        )
    ).scalar_one()
    if orphans:
        raise RuntimeError(
            f"Migration 0005 backfill left {orphans} topic(s) without a module; "
            "refusing to make topics.module_id NOT NULL."
        )

    with op.batch_alter_table("topics") as batch_op:
        batch_op.alter_column("module_id", existing_type=sa.Integer, nullable=False)
        batch_op.drop_column("course")


def downgrade():
    with op.batch_alter_table("topics") as batch_op:
        batch_op.add_column(sa.Column("course", sa.String(255), nullable=True))

    conn = op.get_bind()
    topics_module = sa.table(
        "topics", sa.column("id", sa.Integer), sa.column("module_id", sa.Integer)
    )
    topics_course = sa.table(
        "topics", sa.column("id", sa.Integer), sa.column("course", sa.String)
    )

    rows = conn.execute(
        sa.select(topics_module.c.id, _courses.c.name)
        .select_from(
            topics_module.join(_modules, _modules.c.id == topics_module.c.module_id).join(
                _courses, _courses.c.id == _modules.c.course_id
            )
        )
        .order_by(topics_module.c.id)
    ).fetchall()
    for topic_id, course_name in rows:
        conn.execute(
            topics_course.update()
            .where(topics_course.c.id == topic_id)
            .values(course=course_name)
        )

    with op.batch_alter_table("topics") as batch_op:
        batch_op.alter_column("course", existing_type=sa.String(255), nullable=False)
        batch_op.drop_constraint("fk_topics_module_id", type_="foreignkey")
        batch_op.drop_index("ix_topics_module_id")
        batch_op.drop_column("module_id")
        batch_op.drop_column("position")

    op.drop_table("modules")
    op.drop_table("courses")
