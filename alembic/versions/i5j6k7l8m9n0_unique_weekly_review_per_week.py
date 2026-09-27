"""weekly_reviews: one recap per (user_id, week_start)

Revision ID: i5j6k7l8m9n0
Revises: h4i5j6k7l8m9
Create Date: 2026-09-27

Production gate 1. Both save paths already serialise on the week's trade rows
(`FOR UPDATE`), and take the owner row first so account deletion cannot
deadlock with them; that locking stays. This constraint is the database's own
statement of the invariant, so a future writer that skips the locks fails
loudly instead of creating a second recap.

Existing duplicates are the trader's data. Rather than choose a survivor, the
upgrade counts them and stops, leaving rows and schema untouched; resolve them
deliberately, then rerun. Ownerless legacy rows (`user_id IS NULL`) are
unaffected: NULLs never collide in a unique constraint on SQLite or Postgres.
"""

import sqlalchemy as sa
from alembic import op

revision = "i5j6k7l8m9n0"
down_revision = "h4i5j6k7l8m9"
branch_labels = None
depends_on = None

_NAME = "uq_weekly_reviews_user_week"


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # Hold writers off between the count and ADD CONSTRAINT (released at
        # commit), so a duplicate cannot slip in and surface as a raw error.
        bind.execute(sa.text("LOCK TABLE weekly_reviews IN SHARE MODE"))
    duplicates = bind.execute(
        sa.text(
            "SELECT COUNT(*) FROM ("
            " SELECT user_id, week_start FROM weekly_reviews"
            " WHERE user_id IS NOT NULL"
            " GROUP BY user_id, week_start HAVING COUNT(*) > 1"
            ") AS dup"
        )
    ).scalar()
    if duplicates:
        raise RuntimeError(
            f"weekly_reviews has {duplicates} (user_id, week_start) pair(s) with "
            "more than one row; resolve them before adding the unique constraint. "
            "No row or schema was changed."
        )
    with op.batch_alter_table("weekly_reviews") as batch:
        batch.create_unique_constraint(_NAME, ["user_id", "week_start"])


def downgrade() -> None:
    with op.batch_alter_table("weekly_reviews") as batch:
        batch.drop_constraint(_NAME, type_="unique")
