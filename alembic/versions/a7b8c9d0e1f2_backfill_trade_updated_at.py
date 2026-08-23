"""Backfill trades.updated_at so every existing row is editable.

`PATCH /v1/trades/{id}` decides an edit with ONE conditional UPDATE whose
predicate includes `updated_at = :expected_updated_at`. In SQL, `NULL = x` is
never true for any x — so a row with a NULL `updated_at` can never match the
guard. Such a row reads fine and lists fine, then answers every edit with a
409 carrying `current_updated_at: null`, and there is literally no value a
client can send to get past it. The row is permanently un-editable.

`services/sample_data.load_sample_trades` built its 20 demo trades without a
timestamp (unlike `create_trade`, which setdefaults one), so every sample
trade landed in exactly that state — the first rows a new trader ever tries to
edit. That is fixed at the source; this migration repairs the rows already in
the database, including any legacy row from before `updated_at` was populated.

The fix is deliberately here rather than in the guard. Making
`expected_updated_at` optional and branching on NULL would add a second,
weaker path through the concurrency check — an edit that skips the guard
entirely — which is the one thing the guard exists to make impossible.

Revision ID: a7b8c9d0e1f2
Revises: z6a7b8c9d0e1
"""

from datetime import datetime, timezone

from alembic import op

revision = "a7b8c9d0e1f2"
down_revision = "z6a7b8c9d0e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # `created_at` first: it is the truest "when this row last looked like
    # this" available for a row that was never updated. The migration's own
    # timestamp is the fallback for rows missing that too. Any non-NULL,
    # stable string satisfies the guard — the value only has to be something
    # a client can read back and echo.
    stamp = datetime.now(timezone.utc).isoformat()
    op.execute(
        "UPDATE trades "
        f"SET updated_at = COALESCE(created_at, '{stamp}') "
        "WHERE updated_at IS NULL"
    )


def downgrade() -> None:
    """Intentionally a no-op, and it is the correct downgrade.

    This migration adds no schema to drop; it only repairs data. Restoring
    the previous state would mean writing NULL back into `updated_at`, which
    would re-break every row this fixed — destroying real timestamps for any
    row edited since, and making those trades un-editable again. A downgrade
    that reintroduces the defect it was written to fix is worse than one that
    does nothing, so this leaves the repaired data in place.
    """
