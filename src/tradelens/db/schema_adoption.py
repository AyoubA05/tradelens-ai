"""Canonical schema convergence, shared by both lineages.

Two databases hold the same application but were built by different mechanisms:

* the **tracked** lineage, built by Alembic migrations, ending at r8s9t0u1v2w3
* the **untracked** production-derived lineage, built by
  ``Base.metadata.create_all`` plus ``init_db._reconcile_columns``

They disagree in 18 places, and the disagreement runs in *both* directions —
in two cases the migration lineage is the wrong one. This module defines the
single canonical target and the operations that bring either lineage to it.

It is called from exactly two places, so the DDL exists once:

* ``alembic/versions/t0u1v2w3x4y5_*`` — ``upgrade()``, for the tracked lineage
* ``scripts/adopt_schema.py`` — for the untracked lineage, outside Alembic

Every operation is guarded on the current state, so the module is idempotent and
correct whichever lineage it meets: against production it is mostly additive,
against a freshly migrated database it is mostly a no-op, and running it twice
changes nothing the second time.

PostgreSQL only. SQLite cannot ``ALTER COLUMN SET DEFAULT`` or add a constraint
in place, and both lineages that matter are Neon.
"""

from __future__ import annotations

from typing import List

from sqlalchemy import inspect, text

# Foreign keys, by the name the canonical schema uses. `strategies` takes the
# migration lineage's explicit name because that lineage already has it;
# the other four take PostgreSQL's implicit name because the production lineage
# already has them under it. Converging on names nobody has to change keeps the
# operation additive on both sides.
_FOREIGN_KEYS = (
    ("strategies", "fk_strategies_user_id_users"),
    ("trades", "trades_user_id_fkey"),
    ("corrections", "corrections_user_id_fkey"),
    ("weekly_reviews", "weekly_reviews_user_id_fkey"),
    ("ai_usage_log", "ai_usage_log_user_id_fkey"),
)

# Redundant with each table's PRIMARY KEY index: a second, non-unique btree on
# the same `id` column answers no query the primary key's index cannot, and is
# written on every insert. Only these four are in scope — six more exist on both
# lineages and are therefore not drift; they are deferred to their own cleanup
# revision rather than widening this one.
_REDUNDANT_PK_INDEXES = (
    ("users", "ix_users_id"),
    ("corrections", "ix_corrections_id"),
    ("ai_usage_log", "ix_ai_usage_log_id"),
    ("performance_metrics", "ix_performance_metrics_id"),
)

# Integer columns, not Boolean: 1 means active, 0 means not a sample. The
# canonical schema wants the default enforced by the database, not only by the
# ORM, so a raw INSERT that omits the column still lands on the intended value.
_SERVER_DEFAULTS = (
    ("users", "is_active", "1"),
    ("trades", "is_sample", "0"),
)


class AdoptionPrecheckFailed(RuntimeError):
    """Existing data would violate a constraint this module is about to add."""


class UnsupportedDialect(RuntimeError):
    """Adoption is PostgreSQL-only."""


# ---------------------------------------------------------------------------
# Introspection helpers — SQLAlchemy's inspector, so detection is dialect-neutral
# even though the emitted DDL is not.
# ---------------------------------------------------------------------------


def _tables(conn) -> set:
    return set(inspect(conn).get_table_names())


def _indexes(conn, table: str) -> dict:
    return {i["name"]: i for i in inspect(conn).get_indexes(table)}


def _unique_constraints(conn, table: str) -> set:
    return {
        c["name"] for c in inspect(conn).get_unique_constraints(table) if c.get("name")
    }


def _foreign_key_columns(conn, table: str) -> set:
    return {
        tuple(fk.get("constrained_columns") or ())
        for fk in inspect(conn).get_foreign_keys(table)
    }


def _column(conn, table: str, name: str):
    for col in inspect(conn).get_columns(table):
        if col["name"] == name:
            return col
    return None


# ---------------------------------------------------------------------------
# Username convergence — the one ordering that has to be reasoned about
# ---------------------------------------------------------------------------


def username_convergence_statements(
    *, uq_constraint_present: bool, ix_present: bool, ix_is_unique: bool
) -> List[str]:
    """Statements converging username uniqueness on ONE unique index.

    Target: a single ``UNIQUE INDEX ix_users_username``, no ``uq_users_username``
    constraint, no redundant non-unique index.

    The tracked lineage starts with *both* a ``uq_users_username`` constraint and
    a separate non-unique ``ix_users_username`` — two btree indexes on one
    column for one guarantee. Converging means taking the name
    ``ix_users_username`` from the non-unique index and giving it to a unique one,
    which is a name collision.

    No temporary name is needed, because the collision can be resolved while the
    constraint is still doing the work:

        1. DROP the non-unique index      -> uniqueness held by uq_users_username
        2. CREATE the unique index        -> held by uq_users_username AND the index
        3. DROP the constraint            -> held by the index

    Uniqueness is enforced continuously; at no point between statements is the
    invariant unprotected. Reversing 1 and 2 would collide on the name, and doing
    3 first would leave a window with no unique object at all.

    On the untracked lineage ``ix_users_username`` is already unique and no
    constraint exists, so this returns nothing.
    """
    if not uq_constraint_present and ix_present and ix_is_unique:
        return []  # already canonical

    statements: List[str] = []
    if ix_present and not ix_is_unique:
        statements.append("DROP INDEX ix_users_username")
    if not (ix_present and ix_is_unique):
        statements.append(
            "CREATE UNIQUE INDEX ix_users_username ON users USING btree (username)"
        )
    if uq_constraint_present:
        statements.append("ALTER TABLE users DROP CONSTRAINT uq_users_username")
    return statements


# ---------------------------------------------------------------------------
# Pre-checks
# ---------------------------------------------------------------------------


def preflight(conn) -> List[str]:
    """Return a list of blocking data problems. Empty means safe to adopt.

    Each corresponds to a constraint about to be added. Checked against live
    data rather than assumed from the current row counts, because the counts
    that make them safe today are not a property of the schema.
    """
    problems: List[str] = []
    tables = _tables(conn)

    if "users" in tables:
        dupes = conn.execute(
            text(
                "SELECT count(*) FROM (SELECT lower(trim(email)) AS e FROM users "
                "WHERE email IS NOT NULL AND trim(email) <> '' "
                "GROUP BY lower(trim(email)) HAVING count(*) > 1) d"
            )
        ).scalar()
        if dupes:
            problems.append(
                f"{dupes} duplicate normalised email address(es) — "
                "ix_users_email cannot be created unique"
            )

    if {"strategies", "users"} <= tables:
        orphans = conn.execute(
            text(
                "SELECT count(*) FROM strategies s LEFT JOIN users u ON u.id = s.user_id "
                "WHERE s.user_id IS NOT NULL AND u.id IS NULL"
            )
        ).scalar()
        if orphans:
            problems.append(
                f"{orphans} strategies row(s) reference a missing user — "
                "fk_strategies_user_id_users would fail validation"
            )

        nulls = conn.execute(
            text("SELECT count(*) FROM strategies WHERE is_active IS NULL")
        ).scalar()
        if nulls:
            problems.append(
                f"{nulls} strategies row(s) have NULL is_active — "
                "SET NOT NULL would fail"
            )

    for table, _name in _FOREIGN_KEYS:
        if table == "strategies" or table not in tables:
            continue
        orphans = conn.execute(
            text(
                f"SELECT count(*) FROM {table} t LEFT JOIN users u ON u.id = t.user_id "  # noqa: S608
                "WHERE t.user_id IS NOT NULL AND u.id IS NULL"
            )
        ).scalar()
        if orphans:
            problems.append(f"{orphans} {table} row(s) reference a missing user")

    return problems


# ---------------------------------------------------------------------------
# Adoption
# ---------------------------------------------------------------------------


def plan(conn) -> List[str]:
    """The DDL statements this database needs to reach canonical state.

    Empty means the database is already canonical. Separated from execution so
    the intended change can be shown and reviewed before anything runs.
    """
    statements: List[str] = []
    tables = _tables(conn)

    # -- users -------------------------------------------------------------
    if "users" in tables:
        users_ix = _indexes(conn, "users")

        if "ix_users_email" not in users_ix:
            statements.append(
                "CREATE UNIQUE INDEX ix_users_email ON users USING btree (email)"
            )

        ix_username = users_ix.get("ix_users_username")
        statements.extend(
            username_convergence_statements(
                uq_constraint_present="uq_users_username"
                in _unique_constraints(conn, "users"),
                ix_present=ix_username is not None,
                ix_is_unique=bool(ix_username and ix_username.get("unique")),
            )
        )

    # -- redundant primary-key indexes -------------------------------------
    for table, index in _REDUNDANT_PK_INDEXES:
        if table in tables and index in _indexes(conn, table):
            statements.append(f"DROP INDEX {index}")

    # -- strategies --------------------------------------------------------
    if "strategies" in tables:
        if "ix_strategies_user_id" not in _indexes(conn, "strategies"):
            statements.append(
                "CREATE INDEX ix_strategies_user_id ON strategies "
                "USING btree (user_id)"
            )
        is_active = _column(conn, "strategies", "is_active")
        if is_active is not None and is_active["nullable"]:
            # models.py declares nullable=False; the migration lineage drifted
            # from it. Converge on the model, not on the historical defect.
            statements.append(
                "ALTER TABLE strategies ALTER COLUMN is_active SET NOT NULL"
            )

    # -- trades ------------------------------------------------------------
    if "trades" in tables:
        trades_ix = _indexes(conn, "trades")
        if "ix_trades_user_id" not in trades_ix:
            statements.append(
                "CREATE INDEX ix_trades_user_id ON trades USING btree (user_id)"
            )
        if "ix_trades_trade_hash" not in trades_ix:
            statements.append(
                "CREATE INDEX ix_trades_trade_hash ON trades USING btree (trade_hash)"
            )

    # -- foreign keys ------------------------------------------------------
    for table, name in _FOREIGN_KEYS:
        if table not in tables:
            continue
        if ("user_id",) not in _foreign_key_columns(conn, table):
            statements.append(
                f"ALTER TABLE {table} ADD CONSTRAINT {name} "
                "FOREIGN KEY (user_id) REFERENCES users(id)"
            )

    # -- server defaults ---------------------------------------------------
    for table, column, value in _SERVER_DEFAULTS:
        if table not in tables:
            continue
        col = _column(conn, table, column)
        if col is not None and col.get("default") is None:
            statements.append(
                f"ALTER TABLE {table} ALTER COLUMN {column} SET DEFAULT {value}"
            )

    return statements


def adopt(conn) -> List[str]:
    """Bring this database to canonical state. Returns the statements applied.

    Raises ``AdoptionPrecheckFailed`` when live data would violate a constraint
    being added, rather than letting PostgreSQL fail partway through.
    """
    if conn.dialect.name != "postgresql":
        raise UnsupportedDialect(
            f"Adoption is PostgreSQL-only; got {conn.dialect.name}."
        )

    problems = preflight(conn)
    if problems:
        raise AdoptionPrecheckFailed("; ".join(problems))

    statements = plan(conn)
    for statement in statements:
        conn.execute(text(statement))
    return statements
