"""Make every future trade editable and normalize known legacy outcomes.

The preceding revision backfilled ``trades.updated_at`` once, but left the
column nullable with no database default. Any later raw insert, importer, or
direct ORM construction could therefore recreate a row that no optimistic
PATCH can ever match. This revision turns the concurrency stamp into a
database invariant.

The original seed script also stored lowercase outcome labels. They are real
legacy rows and the strict Phase 3 response enum cannot serialize them. Known
labels are canonicalized without discarding an unknown operator-review value.

Revision ID: b8c9d0e1f2g3
Revises: a7b8c9d0e1f2
"""

from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op

revision = "b8c9d0e1f2g3"
down_revision = "a7b8c9d0e1f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    stamp = datetime.now(timezone.utc).isoformat()
    bind.execute(
        sa.text(
            "UPDATE trades "
            "SET updated_at = COALESCE(created_at, :stamp) "
            "WHERE updated_at IS NULL"
        ),
        {"stamp": stamp},
    )
    bind.execute(
        sa.text(
            "UPDATE trades SET result = CASE LOWER(TRIM(result)) "
            "WHEN 'win' THEN 'Win' "
            "WHEN 'loss' THEN 'Loss' "
            "WHEN 'breakeven' THEN 'Breakeven' "
            "WHEN '' THEN NULL ELSE result END "
            "WHERE result IS NOT NULL"
        )
    )

    # Batch mode works on SQLite and emits the ordinary ALTER on Postgres.
    with op.batch_alter_table("trades") as batch:
        batch.alter_column(
            "updated_at",
            existing_type=sa.String(),
            nullable=False,
            # The existing column is VARCHAR. PostgreSQL requires the default
            # expression to match it, so cast the temporal value explicitly;
            # SQLite accepts the same expression in batch mode.
            server_default=sa.text("CAST(CURRENT_TIMESTAMP AS VARCHAR)"),
        )


def downgrade() -> None:
    # Keep repaired timestamps/outcome spellings; only remove the schema rule.
    with op.batch_alter_table("trades") as batch:
        batch.alter_column(
            "updated_at",
            existing_type=sa.String(),
            nullable=True,
            server_default=None,
        )
