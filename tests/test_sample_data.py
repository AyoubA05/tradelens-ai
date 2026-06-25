"""
Tests for sample/demo trade management (Session A + Session B).

Verifies load/clear/count, that clearing never touches real trades, and that
sample data is scoped per user_id (Session B).
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import src.tradelens.services.sample_data as sample_data
from src.tradelens.db.models import Base, Trade

N = sample_data.SAMPLE_COUNT


@pytest.fixture
def in_memory_db(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    InMemorySession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(sample_data, "SessionLocal", InMemorySession)
    yield InMemorySession
    Base.metadata.drop_all(engine)


def test_load_sample_trades_inserts_flagged(in_memory_db):
    inserted = sample_data.load_sample_trades()
    assert inserted == N == 20
    assert sample_data.count_sample_trades() == N


def test_load_sample_trades_is_idempotent(in_memory_db):
    sample_data.load_sample_trades()
    sample_data.load_sample_trades()  # clears, then reloads — no pile-up
    assert sample_data.count_sample_trades() == N


def test_clear_removes_only_sample_trades(in_memory_db):
    SessionLocal = in_memory_db
    db = SessionLocal()
    db.add(
        Trade(
            asset="NQ",
            result="Win",
            pnl=100.0,
            trade_date="2026-06-01",
            is_sample=0,
        )
    )
    db.commit()
    db.close()

    sample_data.load_sample_trades()
    removed = sample_data.clear_sample_trades()
    assert removed == N

    db = SessionLocal()
    try:
        assert db.query(Trade).count() == 1  # the real trade survives
        assert db.query(Trade).filter(Trade.is_sample == 1).count() == 0
    finally:
        db.close()


def test_sample_data_is_scoped_per_user(in_memory_db):
    sample_data.load_sample_trades(user_id=1)
    sample_data.load_sample_trades(user_id=2)
    assert sample_data.count_sample_trades(user_id=1) == N
    assert sample_data.count_sample_trades(user_id=2) == N

    # Clearing user 1's samples leaves user 2's intact.
    removed = sample_data.clear_sample_trades(user_id=1)
    assert removed == N
    assert sample_data.count_sample_trades(user_id=1) == 0
    assert sample_data.count_sample_trades(user_id=2) == N
