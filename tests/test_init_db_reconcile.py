"""
init_db() must reconcile schema drift, not just create missing tables.

Root cause of the Streamlit Cloud OperationalError (no such column:
trades.trade_process_notes): the deployed SQLite file persists across deploys,
so when a new column is added to a model, create_all() — which only creates
*missing tables* — never adds the column to the already-existing table. The
app then SELECTs a column the physical table lacks and crashes on load.

These tests pin the fix: after create_all(), init_db() adds any model column
missing from an existing table (the automatic form of the historical
`catch_up_schema` migration). Idempotent and a no-op on a fresh DB.
"""

from sqlalchemy import create_engine, inspect, text

from src.tradelens.db import models  # noqa: F401 — register mapped classes
from src.tradelens.db.init_db import init_db
from src.tradelens.db.session import Base


def _columns(engine, table):
    return {c["name"] for c in inspect(engine).get_columns(table)}


def test_init_db_adds_missing_column_to_existing_table(tmp_path):
    url = f"sqlite:///{tmp_path / 'stale.db'}"
    engine = create_engine(url)
    # Full current schema, then simulate a stale deploy: drop a newer column.
    Base.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE trades DROP COLUMN trade_process_notes"))
    assert "trade_process_notes" not in _columns(engine, "trades")

    # init_db must bring the existing table up to the model, not skip it.
    init_db(engine=engine)

    assert "trade_process_notes" in _columns(engine, "trades")


def test_init_db_is_idempotent_on_current_schema(tmp_path):
    url = f"sqlite:///{tmp_path / 'fresh.db'}"
    engine = create_engine(url)
    init_db(engine=engine)
    before = _columns(engine, "trades")
    # Second run must not error or change anything.
    init_db(engine=engine)
    assert _columns(engine, "trades") == before


def test_init_db_default_engine_still_works():
    # Backward-compatible: app.py calls init_db() with no args at import time.
    init_db()
