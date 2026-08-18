"""
Risk & Outcome behavior (Session E1, P1): quick P&L/R save vs exact-price R,
and Direction not being required.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import src.tradelens.services.trade_service as trade_service
from src.tradelens.db.models import Base


def _create(data):
    return trade_service.create_trade(data, user_id=data.get("user_id", 1))


@pytest.fixture
def in_memory_db(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    InMemorySession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(trade_service, "SessionLocal", InMemorySession)
    yield
    Base.metadata.drop_all(engine)


def test_quick_outcome_keeps_manual_r_no_prices(in_memory_db):
    t = _create(
        {
            "asset": "ES",
            "result": "Win",
            "trade_date": "2026-06-26",
            "direction": None,  # not required
            "rr_realized": 2.5,  # manually entered R
            "pnl": 300.0,
        }
    )
    assert t.rr_realized == 2.5
    assert t.pnl == 300.0
    assert t.direction is None  # blank, not required


def test_exact_prices_compute_realized_r(in_memory_db):
    # entry 100, stop 95, exit 110 → realized R = |110-100| / |100-95| = 2.0
    t = _create(
        {
            "asset": "NQ",
            "result": "Win",
            "trade_date": "2026-06-26",
            "direction": None,
            "entry_price": 100.0,
            "stop_price": 95.0,
            "tp_price": 110.0,
            "exit_price": 110.0,
            "rr_realized": None,
        }
    )
    assert t.rr_realized == 2.0
    assert t.rr_planned == 2.0
    assert t.direction is None  # inference happens in the UI, not required here


def test_direction_not_required_to_save(in_memory_db):
    t = _create(
        {
            "asset": "EURUSD",
            "result": "Loss",
            "trade_date": "2026-06-26",
            "pnl": -120.0,
        }
    )
    assert t.id is not None
    assert t.direction is None
