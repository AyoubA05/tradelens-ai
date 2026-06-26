"""
Tests for the Session A dashboard metric fixes:
  * calculate_profit_factor / format_profit_factor — one canonical value, "∞" for
    all-wins (Bug 2: dashboard showed 0.00 while analytics showed ∞).
  * daily_equity_curve — same-day trades aggregate to one dated point (Bug 4).
  * today_pnl — Today's P&L KPI.
"""

import datetime as dt

import pandas as pd

from src.tradelens.services.metrics import (
    calculate_profit_factor,
    compute_basic_metrics,
    compute_expectancy,
    compute_profit_factor_raw,
    daily_equity_curve,
    format_profit_factor,
    today_pnl,
)


def _df(rows):
    return pd.DataFrame(rows)


# ── profit factor ─────────────────────────────────────────────────
def test_profit_factor_all_wins_is_infinity_string():
    df = _df([{"result": "Win", "pnl": 100.0}, {"result": "Win", "pnl": 50.0}])
    assert calculate_profit_factor(df) == "∞"
    assert format_profit_factor(df) == "∞"


def test_profit_factor_with_losses_is_numeric():
    df = _df(
        [
            {"result": "Win", "pnl": 200.0},
            {"result": "Loss", "pnl": -100.0},
        ]
    )
    assert calculate_profit_factor(df) == 2.0
    assert format_profit_factor(df) == "2.00"


def test_profit_factor_empty_is_zero_not_infinity():
    df = _df([])
    assert calculate_profit_factor(df) == 0.0
    assert format_profit_factor(df) == "0.00"


def test_expectancy_calculation():
    # 2 wins (+100 each), 2 losses (-50 each): win_rate=.5, avg_win=100,
    # loss_rate=.5, avg_loss=-50 → expectancy = .5*100 + .5*(-50) = 25.
    df = _df(
        [
            {"result": "Win", "pnl": 100.0},
            {"result": "Win", "pnl": 100.0},
            {"result": "Loss", "pnl": -50.0},
            {"result": "Loss", "pnl": -50.0},
        ]
    )
    assert compute_expectancy(compute_basic_metrics(df)) == 25.0


def test_expectancy_empty_is_zero():
    assert compute_expectancy(compute_basic_metrics(_df([]))) == 0.0


def test_dashboard_and_analytics_agree_on_all_wins():
    """The exact inconsistency from the bug report: never 0.00 when all winners."""
    df = _df([{"result": "Win", "pnl": 300.0}])
    # analytics path (raw float) is inf; the canonical display is ∞ — not 0.00.
    assert compute_profit_factor_raw(df) == float("inf")
    assert format_profit_factor(df) == "∞"


# ── daily equity curve ────────────────────────────────────────────
def test_daily_equity_aggregates_same_day():
    df = _df(
        [
            {"trade_date": "2026-06-15", "pnl": 100.0},
            {"trade_date": "2026-06-15", "pnl": 50.0},  # same day
            {"trade_date": "2026-06-16", "pnl": -30.0},
        ]
    )
    eq = daily_equity_curve(df)
    assert list(eq["trade_date"]) == ["2026-06-15", "2026-06-16"]  # one row per day
    assert list(eq["cumulative_pnl"]) == [150.0, 120.0]


def test_daily_equity_strips_time_component():
    df = _df(
        [
            {"trade_date": "2026-06-15T09:30:00.123456", "pnl": 100.0},
            {"trade_date": "2026-06-15T14:00:00.000000", "pnl": 25.0},
        ]
    )
    eq = daily_equity_curve(df)
    assert list(eq["trade_date"]) == ["2026-06-15"]
    assert eq["cumulative_pnl"].iloc[-1] == 125.0


def test_daily_equity_empty():
    assert daily_equity_curve(pd.DataFrame()).empty


# ── today's P&L ───────────────────────────────────────────────────
def test_today_pnl_sums_only_today():
    today = dt.date(2026, 6, 24)
    df = _df(
        [
            {"trade_date": "2026-06-24", "pnl": 120.0},
            {"trade_date": "2026-06-24", "pnl": -20.0},
            {"trade_date": "2026-06-23", "pnl": 999.0},
        ]
    )
    assert today_pnl(df, today=today) == 100.0


def test_today_pnl_empty_is_zero():
    assert today_pnl(pd.DataFrame(), today=dt.date(2026, 6, 24)) == 0.0
