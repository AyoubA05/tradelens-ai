"""
Migration tests for historical revisions and blank-database round trips.

The full historical chain now replays through Alembic against a fresh SQLite
database. Isolated tests still exercise individual historical migrations where
that is the most direct behavior under test.
"""

import importlib.util
import os
from pathlib import Path
import subprocess
import sys

from alembic.operations import Operations
from alembic.runtime.migration import MigrationContext
from sqlalchemy import create_engine, inspect
from src.tradelens.db.models import Strategy, UserSetting

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


def _run_alembic(args: list[str], database_url: str) -> subprocess.CompletedProcess:
    env = os.environ.copy()
    env["DATABASE_URL"] = database_url
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_blank_sqlite_chain_uses_database_url_and_round_trips_task_one(tmp_path):
    database_path = tmp_path / "alembic-chain.db"
    database_url = f"sqlite:///{database_path}"

    for args in (
        ["upgrade", "head"],
        ["downgrade", "p6q7r8s9t0u1"],
        ["upgrade", "head"],
    ):
        result = _run_alembic(args, database_url)
        assert result.returncode == 0, result.stderr

    engine = create_engine(database_url)
    with engine.connect() as conn:
        inspector = inspect(conn)
        assert database_path.exists()
        assert "user_id" in _columns_of(conn, "strategies")
        assert "user_settings" in _tables(conn)
        unique_names = {
            constraint["name"]
            for constraint in inspector.get_unique_constraints("user_settings")
        }
        assert "uq_user_settings_user_key" in unique_names
        strategy_user_foreign_key = next(
            foreign_key
            for foreign_key in inspector.get_foreign_keys("strategies")
            if foreign_key["constrained_columns"] == ["user_id"]
        )
        assert strategy_user_foreign_key["referred_table"] == "users"
        assert strategy_user_foreign_key["referred_columns"] == ["id"]
        settings_user_foreign_key = next(
            foreign_key
            for foreign_key in inspector.get_foreign_keys("user_settings")
            if foreign_key["constrained_columns"] == ["user_id"]
        )
        assert settings_user_foreign_key["referred_table"] == "users"
        assert settings_user_foreign_key["referred_columns"] == ["id"]
        assert (
            settings_user_foreign_key.get("options", {}).get("ondelete", "").upper()
            == "CASCADE"
        )


def test_full_trade_schema_migration_creates_missing_historical_base_tables(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'historical-base.db'}")
    mig = _load_mig("8383cf3ef6e7_add_full_trade_schema.py")

    with engine.connect() as conn:
        ctx = MigrationContext.configure(conn)
        mig.op = Operations(ctx)

        mig.upgrade()

        assert {"strategies", "trades", "screenshots"} <= _tables(conn)
        assert {"id", "name", "trading_style", "entry_rules"} <= _columns_of(
            conn, "strategies"
        )
        assert {"id", "asset", "strategy_id", "trade_date", "updated_at"} <= _columns(
            conn
        )
        assert {"id", "file_path", "trade_id"} <= _columns_of(conn, "screenshots")


def test_strategy_has_user_owner_column():
    assert "user_id" in Strategy.__table__.columns
    assert Strategy.__table__.columns["user_id"].index


def test_user_setting_has_unique_user_key_pair():
    names = {c.name for c in UserSetting.__table__.constraints}
    assert "uq_user_settings_user_key" in names


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


def test_user_owned_strategy_settings_revision_descends_from_current_head():
    mig = _load_mig("q7r8s9t0u1v2_add_user_owned_strategy_settings.py")
    assert mig.revision == "q7r8s9t0u1v2"
    assert mig.down_revision == "p6q7r8s9t0u1"


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


def test_trade_process_notes_migration_round_trip(tmp_path):
    """Item 8: trades.trade_process_notes — add on upgrade, drop on downgrade."""
    engine = create_engine(f"sqlite:///{tmp_path / 'proc_notes.db'}")
    mig = _load_mig("p6q7r8s9t0u1_add_trade_process_notes.py")
    with engine.connect() as conn:
        conn.exec_driver_sql(
            "CREATE TABLE trades (id INTEGER PRIMARY KEY, asset VARCHAR)"
        )
        ctx = MigrationContext.configure(conn)
        mig.op = Operations(ctx)

        mig.upgrade()
        assert "trade_process_notes" in _columns(conn)
        mig.upgrade()  # idempotent re-run
        mig.downgrade()
        assert "trade_process_notes" not in _columns(conn)
