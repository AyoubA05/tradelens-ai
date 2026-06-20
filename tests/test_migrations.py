"""
Reversibility test for the SMC/ICT migration (g7h8i9j0k1l2).

The full historical chain cannot be replayed from base on a fresh SQLite DB
(a pre-existing condition: the production DB was built via create_all + stamp),
so this test exercises the migration's upgrade()/downgrade() in isolation against
a minimal `trades` table, binding the module's `op` proxy to a live connection.
Proves the migration round-trips on SQLite: add columns -> drop columns -> re-add.
"""

import importlib.util
from pathlib import Path

from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, inspect

ROOT = Path(__file__).resolve().parents[1]
MIGRATION = ROOT / "alembic" / "versions" / "g7h8i9j0k1l2_add_smc_ict_fields.py"
WEEKLY_MIGRATION = ROOT / "alembic" / "versions" / "h8i9j0k1l2m3_add_weekly_reviews.py"

SMC_COLS = {
    "htf_bias",
    "killzone",
    "liquidity_sweep",
    "fvg_used",
    "order_block_used",
    "bos",
    "choch",
    "confirmation_model",
    "entry_type",
    "mistake_tags",
    "followed_rules",
}


def _load_migration():
    spec = importlib.util.spec_from_file_location("smc_migration", MIGRATION)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _load_weekly_migration():
    spec = importlib.util.spec_from_file_location("weekly_migration", WEEKLY_MIGRATION)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _tables(conn) -> set:
    return set(inspect(conn).get_table_names())


def _columns(conn) -> set:
    return {c["name"] for c in inspect(conn).get_columns("trades")}


def test_smc_migration_round_trip(tmp_path):
    url = f"sqlite:///{tmp_path / 'roundtrip.db'}"
    engine = create_engine(url)
    mig = _load_migration()

    with engine.connect() as conn:
        conn.exec_driver_sql(
            "CREATE TABLE trades (id INTEGER PRIMARY KEY, asset VARCHAR)"
        )
        ctx = MigrationContext.configure(conn)
        mig.op = Operations(
            ctx
        )  # bind the `from alembic import op` proxy used inside the module

        mig.upgrade()
        assert SMC_COLS <= _columns(conn), "upgrade() did not add all SMC columns"

        mig.downgrade()
        leftover = SMC_COLS & _columns(conn)
        assert not leftover, f"downgrade() left SMC columns behind: {leftover}"

        mig.upgrade()
        assert SMC_COLS <= _columns(conn), "re-upgrade() did not restore SMC columns"


def test_smc_upgrade_is_idempotent(tmp_path):
    """upgrade() skips columns that already exist (defensive re-run safety)."""
    url = f"sqlite:///{tmp_path / 'idempotent.db'}"
    engine = create_engine(url)
    mig = _load_migration()

    with engine.connect() as conn:
        conn.exec_driver_sql(
            "CREATE TABLE trades (id INTEGER PRIMARY KEY, killzone VARCHAR)"
        )
        ctx = MigrationContext.configure(conn)
        mig.op = Operations(ctx)

        mig.upgrade()  # must not error despite `killzone` pre-existing
        assert SMC_COLS <= _columns(conn)


WEEKLY_COLS = {
    "id",
    "week_start",
    "content_md",
    "thinking_summary",
    "stats_json",
    "cost_usd",
    "created_at",
}


def test_weekly_reviews_migration_round_trip(tmp_path):
    url = f"sqlite:///{tmp_path / 'weekly.db'}"
    engine = create_engine(url)
    mig = _load_weekly_migration()

    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn)
        mig.op = Operations(ctx)

        mig.upgrade()
        assert "weekly_reviews" in _tables(conn), "upgrade() did not create the table"
        assert WEEKLY_COLS <= _columns_of(conn, "weekly_reviews")

        mig.downgrade()
        assert "weekly_reviews" not in _tables(
            conn
        ), "downgrade() left the table behind"

        mig.upgrade()
        assert "weekly_reviews" in _tables(conn), "re-upgrade() did not recreate it"


def test_weekly_reviews_upgrade_is_idempotent(tmp_path):
    """upgrade() is safe to re-run when the table already exists."""
    url = f"sqlite:///{tmp_path / 'weekly_idem.db'}"
    engine = create_engine(url)
    mig = _load_weekly_migration()

    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn)
        mig.op = Operations(ctx)

        mig.upgrade()
        mig.upgrade()  # must not error on second run
        assert "weekly_reviews" in _tables(conn)


def _columns_of(conn, table: str) -> set:
    return {c["name"] for c in inspect(conn).get_columns(table)}
