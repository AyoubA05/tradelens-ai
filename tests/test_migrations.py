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


# ---------------------------------------------------------------------------
# is_sample flag (Session A)
# ---------------------------------------------------------------------------

IS_SAMPLE_MIGRATION = ROOT / "alembic" / "versions" / "i9j0k1l2m3n4_add_is_sample.py"


def _load_is_sample_migration():
    spec = importlib.util.spec_from_file_location(
        "is_sample_migration", IS_SAMPLE_MIGRATION
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_is_sample_migration_round_trip(tmp_path):
    url = f"sqlite:///{tmp_path / 'is_sample.db'}"
    engine = create_engine(url)
    mig = _load_is_sample_migration()

    with engine.connect() as conn:
        conn.exec_driver_sql(
            "CREATE TABLE trades (id INTEGER PRIMARY KEY, asset VARCHAR)"
        )
        ctx = MigrationContext.configure(conn)
        mig.op = Operations(ctx)

        mig.upgrade()
        assert "is_sample" in _columns(conn)

        mig.downgrade()
        assert "is_sample" not in _columns(conn)

        mig.upgrade()
        assert "is_sample" in _columns(conn)


def test_is_sample_upgrade_is_idempotent(tmp_path):
    url = f"sqlite:///{tmp_path / 'is_sample_idem.db'}"
    engine = create_engine(url)
    mig = _load_is_sample_migration()

    with engine.connect() as conn:
        conn.exec_driver_sql(
            "CREATE TABLE trades (id INTEGER PRIMARY KEY, is_sample INTEGER)"
        )
        ctx = MigrationContext.configure(conn)
        mig.op = Operations(ctx)

        mig.upgrade()  # must not error despite is_sample pre-existing
        assert "is_sample" in _columns(conn)


# ---------------------------------------------------------------------------
# Session B migrations: users table, user_id, trade_hash
# ---------------------------------------------------------------------------

VERSIONS = ROOT / "alembic" / "versions"


def _load_mig(filename: str):
    spec = importlib.util.spec_from_file_location("m_" + filename, VERSIONS / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_users_table_migration_round_trip(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'users.db'}")
    mig = _load_mig("j0k1l2m3n4o5_add_users_table.py")
    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn)
        mig.op = Operations(ctx)

        mig.upgrade()
        assert "users" in _tables(conn)
        assert {"id", "username", "password_hash"} <= _columns_of(conn, "users")

        mig.downgrade()
        assert "users" not in _tables(conn)

        mig.upgrade()
        assert "users" in _tables(conn)


def test_user_id_migration_round_trip(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'user_id.db'}")
    mig = _load_mig("k1l2m3n4o5p6_add_user_id_to_trades.py")
    with engine.connect() as conn:
        conn.exec_driver_sql(
            "CREATE TABLE trades (id INTEGER PRIMARY KEY, asset VARCHAR)"
        )
        ctx = MigrationContext.configure(conn)
        mig.op = Operations(ctx)

        mig.upgrade()
        assert "user_id" in _columns(conn)
        mig.upgrade()  # idempotent re-run
        mig.downgrade()
        assert "user_id" not in _columns(conn)


def test_trade_hash_migration_round_trip(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'trade_hash.db'}")
    mig = _load_mig("l2m3n4o5p6q7_add_trade_hash_column.py")
    with engine.connect() as conn:
        conn.exec_driver_sql(
            "CREATE TABLE trades (id INTEGER PRIMARY KEY, asset VARCHAR)"
        )
        ctx = MigrationContext.configure(conn)
        mig.op = Operations(ctx)

        mig.upgrade()
        assert "trade_hash" in _columns(conn)
        mig.upgrade()  # idempotent re-run
        mig.downgrade()
        assert "trade_hash" not in _columns(conn)


def test_corrections_user_id_migration_round_trip(tmp_path):
    """corrections.user_id: upgrade adds column + index; downgrade removes both."""
    engine = create_engine(f"sqlite:///{tmp_path / 'corr_user.db'}")
    mig = _load_mig("n4o5p6q7r8s9_add_user_id_to_corrections.py")
    with engine.connect() as conn:
        conn.exec_driver_sql(
            "CREATE TABLE corrections (id INTEGER PRIMARY KEY, field TEXT)"
        )
        ctx = MigrationContext.configure(conn)
        mig.op = Operations(ctx)

        mig.upgrade()
        assert "user_id" in _columns_of(conn, "corrections")
        idx = {i["name"] for i in inspect(conn).get_indexes("corrections")}
        assert "ix_corrections_user_id" in idx
        mig.upgrade()  # idempotent re-run
        mig.downgrade()
        assert "user_id" not in _columns_of(conn, "corrections")


def test_ai_usage_log_migration_round_trip(tmp_path):
    """ai_usage_log: upgrade creates table + index; downgrade drops it."""
    engine = create_engine(f"sqlite:///{tmp_path / 'ai_usage.db'}")
    mig = _load_mig("o5p6q7r8s9t0_add_ai_usage_log.py")
    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn)
        mig.op = Operations(ctx)

        mig.upgrade()
        assert "ai_usage_log" in _tables(conn)
        assert {"feature", "cost_usd", "user_id"} <= _columns_of(conn, "ai_usage_log")
        mig.upgrade()  # idempotent re-run
        mig.downgrade()
        assert "ai_usage_log" not in _tables(conn)
