import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import src.tradelens.services.trade_service as trade_service
from src.tradelens.db.models import Base
from src.tradelens.services.metrics import compute_basic_metrics, compute_equity_curve


@pytest.fixture
def in_memory_db(monkeypatch):
    """Redirect SessionLocal to an in-memory SQLite DB for the duration of a test."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    InMemorySession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(trade_service, "SessionLocal", InMemorySession)
    yield
    Base.metadata.drop_all(engine)


def test_create_trade_success(in_memory_db):
    trade = trade_service.create_trade({
        "asset": "NQ",
        "result": "Win",
        "pnl": 100.0,
        "trade_date": "2026-01-15",
    })
    assert trade.id is not None
    assert trade.asset == "NQ"


def test_compute_basic_metrics_win_rate():
    df = pd.DataFrame({
        "trade_date": ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04"],
        "pnl":        [100.0,        200.0,        -50.0,        0.0        ],
    })
    m = compute_basic_metrics(df)
    assert m["win_rate"] == 0.5


def test_equity_curve_cumulative():
    df = pd.DataFrame({
        "trade_date": ["2026-01-01", "2026-01-02", "2026-01-03"],
        "pnl":        [100.0,        -50.0,        200.0        ],
    })
    eq = compute_equity_curve(df)
    assert eq["cumulative_pnl"].iloc[-1] == 250.0
