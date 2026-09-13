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
    inserted, _skipped, errors = import_trades_csv(io.BytesIO(csv_bytes), user_id=1)

    assert inserted == 2
    assert errors == []

    rows = trade_service.get_trades(user_id=1)
    assert {r.asset for r in rows} == {"NQ", "ES"}
    assert {r.pnl for r in rows} == {200.0, -90.0}


def test_import_missing_required_columns_returns_error(in_memory_db):
    bad = pd.DataFrame([{"asset": "NQ"}])  # missing trade_date/direction/result/pnl
    inserted, _skipped, errors = import_trades_csv(
        io.BytesIO(bad.to_csv(index=False).encode()), user_id=1
    )
    assert inserted == 0
    assert errors and "missing required columns" in errors[0]


def test_import_corrupt_csv_returns_error(in_memory_db):
    inserted, _skipped, errors = import_trades_csv(
        io.BytesIO(b"\x00\x01 not,a,valid\ncsv\x00"), user_id=1
    )
    assert inserted == 0
    assert errors  # parse or column error reported, never raised


def test_import_reports_bad_rows_individually(in_memory_db, monkeypatch):
    # First row inserts fine; second row raises inside create_trade.
    real_create = trade_service.create_trade
    calls = {"n": 0}

    def flaky_create(data, *, user_id):
        calls["n"] += 1
        if calls["n"] == 2:
            raise ValueError("bad row")
        return real_create(data, user_id=user_id)

    monkeypatch.setattr("src.tradelens.services.csvio.create_trade", flaky_create)
    csv_bytes = export_trades_csv(_sample_df())
    inserted, _skipped, errors = import_trades_csv(io.BytesIO(csv_bytes), user_id=1)

    assert inserted == 1
    assert len(errors) == 1 and "Row 3" in errors[0]


# ── Phase 9, decisions S4 and S5 ──────────────────────────────────────────

import pandas as _pd  # noqa: E402
import pytest as _pytest  # noqa: E402

from src.tradelens.services import csvio as _csvio  # noqa: E402


@_pytest.mark.parametrize("prefix", ["=", "+", "-", "@", "\t", "\r"])
def test_a_formula_leading_text_cell_is_neutralised_and_restored(prefix):
    raw = prefix + 'HYPERLINK("http://x")'
    assert _csvio.neutralise_formula(raw) == "'" + raw
    assert _csvio.restore_formula(_csvio.neutralise_formula(raw)) == raw


@_pytest.mark.parametrize("text", ["took the sweep", "'quoted on purpose", "", "'"])
def test_ordinary_text_is_untouched_both_ways(text):
    assert _csvio.neutralise_formula(text) == text
    assert _csvio.restore_formula(text) == text


def test_numeric_columns_are_never_treated_as_text():
    assert _csvio.NUMERIC_COLUMNS <= set(_csvio.CSV_COLUMNS)
    assert not (_csvio.NUMERIC_COLUMNS & _csvio.TEXT_COLUMNS)
    assert "notes" in _csvio.TEXT_COLUMNS and "pnl" in _csvio.NUMERIC_COLUMNS


def test_export_neutralises_every_text_column_but_not_negative_numbers():
    frame = _pd.DataFrame(
        [
            {
                "notes": "=cmd|' /C calc'!A0",
                "setup_type": "@SUM(A1)",
                "emotions_after": "+1 confident",
                "pnl": -120.5,
                "rr_realized": -1.2,
            }
        ]
    )
    text = _csvio.export_trades_csv(frame).decode("utf-8")
    assert "'=cmd" in text and "'@SUM" in text and "'+1 confident" in text
    assert ",-120.5," in text and "-1.2" in text
    assert "'-120.5" not in text


def test_an_import_over_the_row_cap_inserts_nothing(monkeypatch):
    header = "trade_date,asset,direction,result,pnl\n"
    body = "2026-09-01,NQ,Long,Win,1\n" * (_csvio.MAX_IMPORT_ROWS + 1)
    inserted = []
    monkeypatch.setattr(
        _csvio, "create_trade", lambda data, user_id: inserted.append(data)
    )
    monkeypatch.setattr(_csvio, "trade_hash_exists", lambda h, user_id: False)
    with _pytest.raises(_csvio.TooManyRows):
        _csvio.import_trades_csv_text(header + body, 1)
    assert inserted == []


def test_an_import_exactly_at_the_row_cap_is_allowed(monkeypatch):
    monkeypatch.setattr(_csvio, "MAX_IMPORT_ROWS", 3)
    header = "trade_date,asset,direction,result,pnl\n"
    rows = "".join("2026-09-0%d,NQ,Long,Win,%d\n" % (i + 1, i) for i in range(3))
    inserted = []
    monkeypatch.setattr(
        _csvio, "create_trade", lambda data, user_id: inserted.append(data)
    )
    monkeypatch.setattr(_csvio, "trade_hash_exists", lambda h, user_id: False)
    assert _csvio.import_trades_csv_text(header + rows, 1) == (3, 0, [])
    assert len(inserted) == 3


def test_a_neutralised_export_cell_imports_back_as_the_original_text(monkeypatch):
    header = "trade_date,asset,direction,result,pnl,notes\n"
    row = "2026-09-01,NQ,Long,Win,10,'=not a formula\n"
    inserted = []
    monkeypatch.setattr(
        _csvio, "create_trade", lambda data, user_id: inserted.append(data)
    )
    monkeypatch.setattr(_csvio, "trade_hash_exists", lambda h, user_id: False)
    _csvio.import_trades_csv_text(header + row, 1)
    assert inserted[0]["notes"] == "=not a formula"
