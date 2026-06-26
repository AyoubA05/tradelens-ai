"""
Coverage + behavior tests for csvio.py (Phase 5, week6-d5).

CSV export -> import round-trip and the import error paths. Import persists via
trade_service.create_trade(), so the DB is isolated to in-memory SQLite.
"""

import io

import pandas as pd
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import src.tradelens.services.trade_service as trade_service
from src.tradelens.db.models import Base
from src.tradelens.services.csvio import (
    CSV_COLUMNS,
    export_trades_csv,
    import_trades_csv,
)


@pytest.fixture
def in_memory_db(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    InMemorySession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(trade_service, "SessionLocal", InMemorySession)
    yield
    Base.metadata.drop_all(engine)


def _sample_df():
    return pd.DataFrame(
        [
            {
                "trade_date": "2026-06-15",
                "asset": "NQ",
                "direction": "Long",
                "result": "Win",
                "pnl": 200.0,
            },
            {
                "trade_date": "2026-06-16",
                "asset": "ES",
                "direction": "Short",
                "result": "Loss",
                "pnl": -90.0,
            },
        ]
    )


def test_export_orders_columns():
    csv_bytes = export_trades_csv(_sample_df())
    header = csv_bytes.decode("utf-8").splitlines()[0].split(",")
    assert header == CSV_COLUMNS


def test_export_then_import_round_trip(in_memory_db):
    csv_bytes = export_trades_csv(_sample_df())
    inserted, _skipped, errors = import_trades_csv(io.BytesIO(csv_bytes))

    assert inserted == 2
    assert errors == []

    rows = trade_service.get_trades()
    assert {r.asset for r in rows} == {"NQ", "ES"}
    assert {r.pnl for r in rows} == {200.0, -90.0}


def test_import_missing_required_columns_returns_error(in_memory_db):
    bad = pd.DataFrame([{"asset": "NQ"}])  # missing trade_date/direction/result/pnl
    inserted, _skipped, errors = import_trades_csv(
        io.BytesIO(bad.to_csv(index=False).encode())
    )
    assert inserted == 0
    assert errors and "missing required columns" in errors[0]


def test_import_corrupt_csv_returns_error(in_memory_db):
    inserted, _skipped, errors = import_trades_csv(
        io.BytesIO(b"\x00\x01 not,a,valid\ncsv\x00")
    )
    assert inserted == 0
    assert errors  # parse or column error reported, never raised


def test_import_reports_bad_rows_individually(in_memory_db, monkeypatch):
    # First row inserts fine; second row raises inside create_trade.
    real_create = trade_service.create_trade
    calls = {"n": 0}

    def flaky_create(data):
        calls["n"] += 1
        if calls["n"] == 2:
            raise ValueError("bad row")
        return real_create(data)

    monkeypatch.setattr("src.tradelens.services.csvio.create_trade", flaky_create)
    csv_bytes = export_trades_csv(_sample_df())
    inserted, _skipped, errors = import_trades_csv(io.BytesIO(csv_bytes))

    assert inserted == 1
    assert len(errors) == 1 and "Row 3" in errors[0]
