"""Live Postgres compatibility — skipped unless TRADELENS_PG_TEST_URL is set.

Run against a scratch Neon/Postgres DB:
    TRADELENS_PG_TEST_URL="postgresql://user:pass@host/db?sslmode=require" \
        pytest tests/test_postgres_integration.py -v

Proves the SQLite-authored schema (create_all) + the reconcile path + a basic
insert/select all work on Postgres. Not part of the default hermetic suite.
"""

import os

import pytest

PG_URL = os.getenv("TRADELENS_PG_TEST_URL")
PG_ALLOW_DROP = os.getenv("TRADELENS_PG_TEST_ALLOW_DROP") == "1"
pytestmark = pytest.mark.skipif(
    not PG_URL or not PG_ALLOW_DROP,
    reason=(
        "set TRADELENS_PG_TEST_URL and TRADELENS_PG_TEST_ALLOW_DROP=1 to run "
        "Postgres integration tests (they drop the app schema)"
    ),
)


def _fresh_engine():
    import sys
    from pathlib import Path

    from sqlalchemy import text

    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from pg_guard import require_disposable_database

    require_disposable_database(PG_URL)  # before drop_all

    from src.tradelens.db import models  # noqa: F401 — register tables
    from src.tradelens.db.session import Base, build_engine

    eng = build_engine(PG_URL)
    # Clean slate: drop the app schema so reruns are deterministic.
    Base.metadata.drop_all(eng)
    with eng.begin() as c:
        c.execute(text("SELECT 1"))
    return eng


def test_create_all_and_reconcile_on_postgres():
    from sqlalchemy import inspect

    from src.tradelens.db.init_db import init_db
    from src.tradelens.db.session import Base

    eng = _fresh_engine()
    init_db(engine=eng, allow_unmanaged_remote=True)  # deliberate fresh bootstrap
    tables = set(inspect(eng).get_table_names())
    assert "trades" in tables
    cols = {c["name"] for c in inspect(eng).get_columns("trades")}
    assert "trade_process_notes" in cols  # the SP1 reconcile column
    Base.metadata.drop_all(eng)


def test_trade_round_trip_on_postgres():
    from sqlalchemy.orm import sessionmaker

    from src.tradelens.db.init_db import init_db
    from src.tradelens.db.models import Trade
    from src.tradelens.db.session import Base

    eng = _fresh_engine()
    init_db(engine=eng, allow_unmanaged_remote=True)
    Session = sessionmaker(bind=eng)
    with Session() as s:
        s.add(Trade(trade_date="2026-07-16", asset="NQ", direction="Long"))
        s.commit()
    with Session() as s:
        rows = s.query(Trade).all()
        assert len(rows) == 1
        assert rows[0].asset == "NQ"
    Base.metadata.drop_all(eng)
