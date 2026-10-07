"""store emails in lower case, one account per address

Revision ID: 0011
Revises: 0010
Create Date: 2026-10-09

Sign-in used to compare emails exactly, so Alice@example.com and alice@example.com
were two different accounts and typing the "wrong" capitalisation looked like a wrong
password. Emails are now stored trimmed and lower-case and matched without regard to
capitalisation.

This migration lower-cases every stored email and adds a unique index on lower(email)
so the database itself refuses a second account that differs only by capitalisation.

If two existing accounts already differ only by capitalisation they cannot be merged
automatically (they may hold different courses and scores), so the migration stops
BEFORE changing anything and names them: delete or merge one by hand, then run it again.

Written with plain table definitions, not app.models. Downgrade drops the index; the
emails stay lower-case (the original capitalisation is not kept anywhere).
"""
from collections import defaultdict

from alembic import op
import sqlalchemy as sa

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

_users = sa.table("users", sa.column("id", sa.Integer), sa.column("email", sa.String))


def upgrade():
    conn = op.get_bind()
    rows = conn.execute(sa.select(_users.c.id, _users.c.email)).fetchall()

    groups = defaultdict(list)
    for user_id, email in rows:
        groups[(email or "").strip().lower()].append((user_id, email))
    clashes = {key: members for key, members in groups.items() if len(members) > 1}
    if clashes:
        lines = [
            "  " + ", ".join(f"{email!r} (account id {user_id})" for user_id, email in members)
            for members in clashes.values()
        ]
        raise RuntimeError(
            "Cannot store emails in lower case: these accounts differ only by capitalisation, "
            "and which one to keep is your decision (they may own different courses):\n"
            + "\n".join(lines)
            + "\nDelete or merge one of each pair, then run `alembic upgrade head` again. "
            "Nothing was changed."
        )

    for user_id, email in rows:
        cleaned = (email or "").strip().lower()
        if cleaned != email:
            conn.execute(_users.update().where(_users.c.id == user_id).values(email=cleaned))

    op.create_index("uq_users_email_lower", "users", [sa.text("lower(email)")], unique=True)


def downgrade():
    op.drop_index("uq_users_email_lower", table_name="users")
