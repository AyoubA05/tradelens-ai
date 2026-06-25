"""
Tests for sample/demo trade management (Session A, Section 4).

Verifies load/clear/count and — critically — that clearing sample trades never
touches real trades.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import src.tradelens.services.sample_data as sample_data
from src.tradelens.db.models import Base, Trade


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
    assert inserted == 60
    assert sample_data.count_sample_trades() == 60


def test_load_sample_trades_is_idempotent(in_memory_db):
    sample_data.load_sample_trades()
    sample_data.load_sample_trades()  # clears, then reloads — no pile-up
    assert sample_data.count_sample_trades() == 60


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
    assert removed == 60

    db = SessionLocal()
    try:
        assert db.query(Trade).count() == 1  # the real trade survives
        assert db.query(Trade).filter(Trade.is_sample == 1).count() == 0
    finally:
        db.close()
