"""Converge the tracked lineage on canonical schema state.

Production was built by ``create_all`` + ``_reconcile_columns``, never by
Alembic, so the two lineages disagree in 18 places — and in two of them the
*migration* lineage is the wrong side. This revision moves the tracked lineage
onto the canonical target; ``scripts/adopt_schema.py`` moves the untracked one,
using the same operations from ``db/schema_adoption.py`` so the DDL exists once.

What this revision changes on a database built by migrations:

* adds the four ``user_id`` foreign keys the migrations never created
  (``trades``, ``corrections``, ``weekly_reviews``, ``ai_usage_log``)
* adds ``ix_trades_user_id`` and ``ix_trades_trade_hash``
* tightens ``strategies.is_active`` to ``NOT NULL``, matching ``models.py:91``
* converges username uniqueness on one unique index, dropping the redundant
  ``uq_users_username`` constraint

It is a no-op for everything the tracked lineage already has.

Why the untracked lineage is not simply stamped at r8 and upgraded: it is
knowingly *not* equivalent to r8, and stamping it there would assert something
false. Instead it is reconciled directly, compared against a database built by
migrations to exactly this revision, and stamped at **this** revision only once
that comparison comes back empty.

Revision ID: t0u1v2w3x4y5
Revises: r8s9t0u1v2w3
Create Date: 2026-08-11
"""

from typing import Sequence, Union

from alembic import op

from src.tradelens.db.schema_adoption import adopt

revision: str = "t0u1v2w3x4y5"
down_revision: Union[str, Sequence[str], None] = "r8s9t0u1v2w3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()

    # PostgreSQL only, and a deliberate no-op elsewhere.
    #
    # This revision reconciles two *PostgreSQL* lineages: the Neon production
    # database and the Neon reference built by migrations. Half of what it does
    # — ALTER COLUMN SET DEFAULT, ADD CONSTRAINT in place, SET NOT NULL — SQLite
    # cannot express at all, and a SQLite database is never one of the two
    # lineages being converged.
    #
    # Skipping rather than raising is what keeps the migration chain runnable on
    # SQLite, which local development and the test suite both depend on. A
    # SQLite database does not reach canonical state, and is not expected to.
    if conn.dialect.name != "postgresql":
        return

    # Same function scripts/adopt_schema.py calls. Every operation inside is
    # guarded on current state, so this is idempotent and does not care which
    # lineage it is applied to.
    adopt(conn)


def downgrade() -> None:
    """Return the tracked lineage to its r8 shape.

    Deliberately *not* a call into schema_adoption: adoption converges toward a
    single target from either direction, which is not something that can be
    mechanically reversed. This spells out the reverse for the one lineage a
    downgrade can mean anything for — a database that reached here by running
    upgrade() on top of r8.

    Guarded throughout, so it converges rather than erroring if run against a
    database that only partly matches.
    """
    conn = op.get_bind()
    from sqlalchemy import inspect, text

    # Mirrors upgrade(): nothing was done on SQLite, so nothing is undone.
    if conn.dialect.name != "postgresql":
        return

    inspector = inspect(conn)
    tables = set(inspector.get_table_names())

    def indexes(table):
        return {i["name"] for i in inspect(conn).get_indexes(table)}

    def fk_columns(table):
        return {
            tuple(fk.get("constrained_columns") or ())
            for fk in inspect(conn).get_foreign_keys(table)
        }

    # Username: restore the constraint BEFORE weakening the index, so
    # uniqueness is continuously enforced in this direction too.
    if "users" in tables:
        if "uq_users_username" not in {
            c["name"] for c in inspector.get_unique_constraints("users")
        }:
            conn.execute(
                text(
                    "ALTER TABLE users ADD CONSTRAINT uq_users_username "
                    "UNIQUE (username)"
                )
            )
        if "ix_users_username" in indexes("users"):
            conn.execute(text("DROP INDEX ix_users_username"))
        conn.execute(
            text("CREATE INDEX ix_users_username ON users USING btree (username)")
        )
        if "ix_users_email" in indexes("users"):
            conn.execute(text("DROP INDEX ix_users_email"))

    if "strategies" in tables:
        conn.execute(
            text("ALTER TABLE strategies ALTER COLUMN is_active DROP NOT NULL")
        )

    for table, name in (
        ("trades", "trades_user_id_fkey"),
        ("corrections", "corrections_user_id_fkey"),
        ("weekly_reviews", "weekly_reviews_user_id_fkey"),
        ("ai_usage_log", "ai_usage_log_user_id_fkey"),
    ):
        if table in tables and ("user_id",) in fk_columns(table):
            conn.execute(text(f"ALTER TABLE {table} DROP CONSTRAINT {name}"))

    if "trades" in tables:
        for index in ("ix_trades_user_id", "ix_trades_trade_hash"):
            if index in indexes("trades"):
                conn.execute(text(f"DROP INDEX {index}"))

    # The four redundant primary-key indexes are NOT recreated. They never
    # existed in the tracked lineage that this downgrade returns to, and
    # recreating a redundant index on the way back would be restoring a defect.
