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
    trade = trade_service.create_trade(
        {
            "asset": "NQ",
            "result": "Win",
            "pnl": 100.0,
            "trade_date": "2026-01-15",
        }
    )
    assert trade.id is not None
    assert trade.asset == "NQ"


def test_compute_basic_metrics_win_rate():
    df = pd.DataFrame(
        {
            "trade_date": ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04"],
            "pnl": [100.0, 200.0, -50.0, 0.0],
        }
    )
    m = compute_basic_metrics(df)
    assert m["win_rate"] == 0.5


def test_equity_curve_cumulative():
    df = pd.DataFrame(
        {
            "trade_date": ["2026-01-01", "2026-01-02", "2026-01-03"],
            "pnl": [100.0, -50.0, 200.0],
        }
    )
    eq = compute_equity_curve(df)
    assert eq["cumulative_pnl"].iloc[-1] == 250.0


# ---------------------------------------------------------------------------
# create_trade — derived fields + key filtering
# ---------------------------------------------------------------------------


def test_create_trade_derives_day_of_week(in_memory_db):
    t = trade_service.create_trade(
        {"asset": "NQ", "result": "Win", "pnl": 1.0, "trade_date": "2026-06-15"}
    )
    assert t.day_of_week == "Monday"


def test_create_trade_invalid_date_no_day_of_week(in_memory_db):
    t = trade_service.create_trade(
        {"asset": "NQ", "result": "Win", "pnl": 1.0, "trade_date": "not-a-date"}
    )
    assert t.day_of_week is None


def test_create_trade_computes_rr_long(in_memory_db):
    t = trade_service.create_trade(
        {
            "asset": "NQ",
            "result": "Win",
            "trade_date": "2026-06-15",
            "direction": "Long",
            "entry_price": 100.0,
            "stop_price": 90.0,
            "tp_price": 130.0,
            "exit_price": 120.0,
        }
    )
    assert t.rr_planned == 3.0  # reward 30 / risk 10
    assert t.rr_realized == 2.0  # reward 20 / risk 10


def test_create_trade_zero_risk_rr_none(in_memory_db):
    t = trade_service.create_trade(
        {
            "asset": "NQ",
            "result": "Breakeven",
            "trade_date": "2026-06-15",
            "direction": "Long",
            "entry_price": 100.0,
            "stop_price": 100.0,  # zero risk
            "tp_price": 130.0,
            "exit_price": 120.0,
        }
    )
    assert t.rr_planned is None and t.rr_realized is None


def test_create_trade_strips_unknown_keys(in_memory_db):
    t = trade_service.create_trade(
        {
            "asset": "NQ",
            "result": "Win",
            "pnl": 1.0,
            "trade_date": "2026-06-15",
            "not_a_real_column": "ignored",
        }
    )
    assert t.id is not None
    assert not hasattr(t, "not_a_real_column")


# ---------------------------------------------------------------------------
# get_trades — filters
# ---------------------------------------------------------------------------


def _seed_three(in_memory_db):
    trade_service.create_trade(
        {
            "asset": "NQ",
            "result": "Win",
            "pnl": 100.0,
            "trade_date": "2026-06-10",
            "session": "NY AM",
            "strategy_used": "ICT OB",
        }
    )
    trade_service.create_trade(
        {
            "asset": "ES",
            "result": "Loss",
            "pnl": -50.0,
            "trade_date": "2026-06-15",
            "session": "London",
            "strategy_used": "FVG",
        }
    )
    trade_service.create_trade(
        {
            "asset": "BTCUSD",
            "result": "Win",
            "pnl": 200.0,
            "trade_date": "2026-06-20",
            "session": "NY AM",
            "strategy_used": "ICT OB",
        }
    )


def test_get_trades_date_range(in_memory_db):
    _seed_three(in_memory_db)
    rows = trade_service.get_trades(start_date="2026-06-12", end_date="2026-06-18")
    assert [r.asset for r in rows] == ["ES"]


def test_get_trades_filters_asset_result_session_strategy(in_memory_db):
    _seed_three(in_memory_db)
    assert {r.asset for r in trade_service.get_trades(asset="NQ")} == {"NQ"}
    assert {r.asset for r in trade_service.get_trades(result="Win")} == {"NQ", "BTCUSD"}
    assert {r.asset for r in trade_service.get_trades(session="London")} == {"ES"}
    assert {r.asset for r in trade_service.get_trades(strategy="ICT")} == {
        "NQ",
        "BTCUSD",
    }


def test_get_trades_result_all_is_ignored(in_memory_db):
    _seed_three(in_memory_db)
    assert len(trade_service.get_trades(result="All")) == 3


def test_get_trades_orders_recent_first(in_memory_db):
    _seed_three(in_memory_db)
    dates = [r.trade_date for r in trade_service.get_trades()]
    assert dates == ["2026-06-20", "2026-06-15", "2026-06-10"]


# ---------------------------------------------------------------------------
# get_primary_screenshot
# ---------------------------------------------------------------------------


def test_get_primary_screenshot_none_for_no_screenshot(in_memory_db):
    t = trade_service.create_trade(
        {"asset": "NQ", "result": "Win", "pnl": 1.0, "trade_date": "2026-06-15"}
    )
    assert trade_service.get_primary_screenshot(t.id) is None


def test_get_primary_screenshot_none_id(in_memory_db):
    assert trade_service.get_primary_screenshot(None) is None


def test_get_primary_screenshot_returns_path(in_memory_db):
    from src.tradelens.db.models import Screenshot

    t = trade_service.create_trade(
        {"asset": "NQ", "result": "Win", "pnl": 1.0, "trade_date": "2026-06-15"}
    )
    db = trade_service.SessionLocal()
    db.add(Screenshot(trade_id=t.id, file_path="/tmp/shot.png"))
    db.commit()
    db.close()
    assert trade_service.get_primary_screenshot(t.id) == "/tmp/shot.png"


def test_prices_store_and_retrieve_without_precision_loss(in_memory_db):
    """Item 7: 3.496 and 3.3765 must round-trip unmodified (no rounding/cap)."""
    from src.tradelens.services.trade_service import create_trade, get_trade

    trade = create_trade(
        {
            "trade_date": "2026-07-03",
            "asset": "NG",
            "result": "Win",
            "entry_price": 3.496,
            "stop_price": 3.3765,
            "tp_price": 3.5125,
            "exit_price": 3.4995,
        }
    )
    row = get_trade(trade.id, user_id=None)
    assert row.entry_price == 3.496
    assert row.stop_price == 3.3765
    assert row.tp_price == 3.5125
    assert row.exit_price == 3.4995


def test_trade_process_notes_stores_and_retrieves(in_memory_db):
    """Item 8: the mechanical process notes persist as their own field."""
    from src.tradelens.services.trade_service import create_trade, get_trade

    note = "Swept liquidity, broke structure, moved to BE after 2nd IFVG break."
    trade = create_trade(
        {
            "trade_date": "2026-07-03",
            "asset": "MNQ",
            "result": "Win",
            "trade_process_notes": note,
        }
    )
    row = get_trade(trade.id, user_id=None)
    assert row.trade_process_notes == note


def test_get_trade_relationships_usable_after_session_closes(in_memory_db):
    """Item 11 regression: get_trade closes its session, so screenshots AND
    ai_analysis must be eager-loaded — touching them later must not raise
    DetachedInstanceError (the Journal detail-panel error)."""
    from src.tradelens.db.models import AIAnalysis
    from src.tradelens.services.trade_service import create_trade, get_trade

    trade = create_trade({"trade_date": "2026-07-03", "asset": "MNQ", "result": "Win"})
    db = trade_service.SessionLocal()  # the fixture's monkeypatched sessionmaker
    db.add(AIAnalysis(trade_id=trade.id, bias="bullish", trade_quality=7))
    db.commit()
    db.close()

    row = get_trade(trade.id, user_id=None)
    assert row.screenshots == []  # off-session access must not raise
    analysis = row.ai_analysis  # was DetachedInstanceError before the fix
    assert analysis is not None
    assert analysis.bias == "bullish"


def test_create_trade_rejects_outcome_contradicting_pnl(in_memory_db):
    """A Win with a negative P&L would corrupt every outcome-based metric."""
    from src.tradelens.services.trade_validation import OutcomeMismatch

    with pytest.raises(OutcomeMismatch):
        trade_service.create_trade(
            {
                "asset": "NQ",
                "result": "Win",
                "pnl": -500.0,
                "trade_date": "2026-07-18",
            }
        )


def test_create_trade_derives_result_from_pnl_when_absent(in_memory_db):
    trade = trade_service.create_trade(
        {"asset": "NQ", "pnl": -120.0, "trade_date": "2026-07-18"}
    )
    assert trade.result == "Loss"


def test_create_trade_keeps_manual_result_without_pnl(in_memory_db):
    trade = trade_service.create_trade(
        {"asset": "NQ", "result": "Breakeven", "trade_date": "2026-07-18"}
    )
    assert trade.result == "Breakeven"
    assert trade.pnl is None


def test_update_trade_rejects_contradiction_against_stored_pnl(in_memory_db):
    """Editing only the label must be validated against the row's stored P&L."""
    from src.tradelens.services.trade_validation import OutcomeMismatch

    trade = trade_service.create_trade(
        {"asset": "NQ", "result": "Loss", "pnl": -500.0, "trade_date": "2026-07-18"}
    )
    with pytest.raises(OutcomeMismatch):
        trade_service.update_trade(trade.id, None, result="Win")


def test_update_trade_relabels_when_pnl_flips_sign(in_memory_db):
    trade = trade_service.create_trade(
        {"asset": "NQ", "result": "Loss", "pnl": -500.0, "trade_date": "2026-07-18"}
    )
    updated = trade_service.update_trade(trade.id, None, pnl=250.0)
    assert updated.result == "Win"
    assert updated.pnl == 250.0
