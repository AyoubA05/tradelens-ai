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
    inserted = sample_data.load_sample_trades(1)
    assert inserted == N == 20
    assert sample_data.count_sample_trades(1) == N


def test_load_sample_trades_is_idempotent(in_memory_db):
    sample_data.load_sample_trades(1)
    sample_data.load_sample_trades(1)  # clears, then reloads — no pile-up
    assert sample_data.count_sample_trades(1) == N


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

    sample_data.load_sample_trades(1)
    removed = sample_data.clear_sample_trades(1)
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


# ---------------------------------------------------------------------------
# Sample trades carry the active strategy (Task 11 correction)
# ---------------------------------------------------------------------------


@pytest.fixture
def db_with_strategy(monkeypatch):
    """One in-memory database shared by sample_data and the strategy service,
    so a profile written by one is visible to the other."""
    import src.tradelens.services.strategy as strategy

    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(sample_data, "SessionLocal", Session)
    monkeypatch.setattr(strategy, "SessionLocal", Session)
    yield Session
    Base.metadata.drop_all(engine)


def test_sample_trades_carry_the_active_strategy(db_with_strategy):
    """New Trade stamps strategy_used from the active playbook on every real
    trade. Sample data that omits it produces rows no logging flow could
    create, and leaves Analytics' Strategy filter permanently empty for
    anyone exploring the product with sample data."""
    from src.tradelens.services.strategy import upsert_strategy_profile

    upsert_strategy_profile(1, name="ICT/SMC Day Trading")
    sample_data.load_sample_trades(1)

    session = db_with_strategy()
    try:
        names = {t.strategy_used for t in session.query(Trade).all()}
    finally:
        session.close()
    assert names == {"ICT/SMC Day Trading"}, names


def test_sample_trades_load_without_a_strategy(db_with_strategy):
    """A user with no playbook still gets sample data; the column stays
    empty rather than the load failing."""
    assert sample_data.load_sample_trades(2) > 0

    session = db_with_strategy()
    try:
        assert all(t.strategy_used is None for t in session.query(Trade).all())
    finally:
        session.close()
