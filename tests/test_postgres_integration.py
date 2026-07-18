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
pytestmark = pytest.mark.skipif(
    not PG_URL, reason="set TRADELENS_PG_TEST_URL to run Postgres integration tests"
)


def _fresh_engine():
    from sqlalchemy import text

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
    init_db(engine=eng)  # create_all + reconcile
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
    init_db(engine=eng)
    Session = sessionmaker(bind=eng)
    with Session() as s:
        s.add(Trade(trade_date="2026-07-16", asset="NQ", direction="Long"))
        s.commit()
    with Session() as s:
        rows = s.query(Trade).all()
        assert len(rows) == 1
        assert rows[0].asset == "NQ"
    Base.metadata.drop_all(eng)
