"""
Duplicate-trade prevention (Session B, Section 1).

Covers the trade_hash fingerprint, the recent-duplicate lookup that powers the
"is this a duplicate?" prompt, and CSV-import dedup.
"""

import io

import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import src.tradelens.services.csvio as csvio
import src.tradelens.services.trade_service as trade_service
from src.tradelens.db.models import Base, Trade


@pytest.fixture
def db_session(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    InMemorySession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    # Both csvio and trade_service resolve SessionLocal through trade_service.
    monkeypatch.setattr(trade_service, "SessionLocal", InMemorySession)
    yield InMemorySession
    Base.metadata.drop_all(engine)


_TRADE = {
    "trade_date": "2026-06-20",
    "asset": "NQ",
    "direction": "Long",
    "entry_price": 19850.25,
    "stop_price": 19820.0,
    "exit_price": 19920.0,
    "pnl": 700.0,
    "result": "Win",
}


def test_trade_hash_is_stable_and_identifying():
    a = trade_service.compute_trade_hash(_TRADE)
    b = trade_service.compute_trade_hash(dict(_TRADE))
    assert a == b
    different = trade_service.compute_trade_hash({**_TRADE, "pnl": 100.0})
    assert a != different


def test_recent_duplicate_detected(db_session):
    trade_service.create_trade(dict(_TRADE))
    dup = trade_service.find_recent_duplicate(dict(_TRADE), within_seconds=60)
    assert dup is not None
    assert dup.asset == "NQ"


def test_duplicate_trade_not_created(db_session):
    """The UI flow: detect the recent duplicate and skip the second insert."""
    trade_service.create_trade(dict(_TRADE))
    if trade_service.find_recent_duplicate(dict(_TRADE)) is None:
        trade_service.create_trade(dict(_TRADE))
    db = db_session()
    try:
        assert db.query(Trade).count() == 1
    finally:
        db.close()


def test_no_false_positive_for_distinct_trade(db_session):
    trade_service.create_trade(dict(_TRADE))
    other = {**_TRADE, "asset": "ES", "pnl": -200.0}
    assert trade_service.find_recent_duplicate(other) is None


def test_csv_import_skips_duplicates(db_session):
    # Pre-existing trade in the DB, plus a CSV that repeats it twice + one new row.
    trade_service.create_trade(dict(_TRADE))
    rows = [
        _TRADE,  # duplicate of the existing row
        _TRADE,  # duplicate within the file
        {**_TRADE, "asset": "EURUSD", "pnl": 120.0},  # genuinely new
    ]
    csv_bytes = pd.DataFrame(rows).to_csv(index=False).encode()
    inserted, skipped, errors = csvio.import_trades_csv(io.BytesIO(csv_bytes))
    assert inserted == 1
    assert skipped == 2
    assert errors == []
    db = db_session()
    try:
        assert db.query(Trade).count() == 2
    finally:
        db.close()
