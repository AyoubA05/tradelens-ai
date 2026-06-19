"""
Tests for the extended metrics engine — hardcoded DataFrames only.
No DB, no mocks, no network.
"""
import pandas as pd
import pytest

from src.tradelens.services.metrics import (
    by_asset,
    by_day_of_week,
    by_hour_of_day,
    by_session,
    by_setup_type,
    by_strategy,
    calendar_daily_pnl,
    compute_basic_metrics,
    compute_breakdown,
    compute_equity_curve,
    compute_expectancy,
    compute_max_drawdown,
    compute_profit_factor_raw,
    compute_streaks,
    confirmation_model_performance,
    daily_pnl,
    drawdown_series,
    emotion_vs_rr,
    equity_curve_series,
    killzone_performance,
    mistake_frequency,
    r_multiple_distribution,
)


# ---------------------------------------------------------------------------
# compute_expectancy
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# compute_profit_factor_raw
# ---------------------------------------------------------------------------

def test_compute_profit_factor_raw_all_wins():
    df = pd.DataFrame({
        "result": ["Win", "Win"],
        "pnl":    [200.0, 300.0],
    })
    assert compute_profit_factor_raw(df) == float("inf")


def test_compute_profit_factor_raw_mixed():
    df = pd.DataFrame({
        "result": ["Win", "Win", "Loss", "Loss"],
        "pnl":    [200.0, 300.0, -50.0, -100.0],
    })
    # sum_wins=500, sum_losses=150 → 500/150 ≈ 3.333
    assert compute_profit_factor_raw(df) == pytest.approx(500.0 / 150.0, abs=1e-6)


def test_compute_profit_factor_raw_empty():
    assert compute_profit_factor_raw(pd.DataFrame()) == 0.0


def test_compute_profit_factor_raw_only_losses():
    df = pd.DataFrame({
        "result": ["Loss", "Loss"],
        "pnl":    [-100.0, -200.0],
    })
    assert compute_profit_factor_raw(df) == 0.0


# ---------------------------------------------------------------------------
# compute_expectancy
# ---------------------------------------------------------------------------

def test_expectancy_positive():
    metrics = compute_basic_metrics(pd.DataFrame({
        "result": ["Win", "Win", "Win", "Loss"],
        "pnl":    [200.0, 150.0, 100.0, -50.0],
    }))
    e = compute_expectancy(metrics)
    # win_rate=0.75, avg_win=150, loss_rate=0.25, avg_loss=-50
    # expectancy = 0.75*150 + 0.25*(-50) = 112.5 - 12.5 = 100.0
    assert e == pytest.approx(100.0, abs=1e-6)


def test_expectancy_negative():
    metrics = compute_basic_metrics(pd.DataFrame({
        "result": ["Loss", "Loss", "Loss", "Win"],
        "pnl":    [-200.0, -150.0, -100.0, 50.0],
    }))
    e = compute_expectancy(metrics)
    assert e < 0.0


def test_expectancy_zero_on_empty_metrics():
    assert compute_expectancy({"total_trades": 0, "win_rate": 0.0, "loss_rate": 0.0,
                                "avg_win": 0.0, "avg_loss": 0.0}) == 0.0


def test_expectancy_missing_key():
    # Missing "total_trades" — should return 0.0, not raise
    assert compute_expectancy({"win_rate": 0.6, "avg_win": 100.0}) == 0.0


def test_expectancy_breakeven_only():
    metrics = compute_basic_metrics(pd.DataFrame({
        "result": ["Breakeven", "Breakeven"],
        "pnl":    [0.0, 0.0],
    }))
    assert compute_expectancy(metrics) == 0.0


# ---------------------------------------------------------------------------
# compute_max_drawdown
# ---------------------------------------------------------------------------

def test_max_drawdown_known_drop():
    # cumulative PnL goes: 100 → 80 → 90 → 70
    # peak = 100, trough = 70 → max drawdown = 30
    curve = pd.DataFrame({
        "trade_date": ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04"],
        "pnl":        [100.0,        -20.0,         10.0,         -20.0],
        "cumulative_pnl": [100.0,    80.0,          90.0,         70.0],
    })
    assert compute_max_drawdown(curve) == pytest.approx(30.0, abs=1e-6)


def test_max_drawdown_flat():
    curve = pd.DataFrame({
        "trade_date": ["2026-01-01", "2026-01-02", "2026-01-03"],
        "pnl":        [100.0, 50.0, 75.0],
        "cumulative_pnl": [100.0, 150.0, 225.0],
    })
    assert compute_max_drawdown(curve) == 0.0


def test_max_drawdown_empty():
    empty_curve = pd.DataFrame(columns=["trade_date", "pnl", "cumulative_pnl"])
    assert compute_max_drawdown(empty_curve) == 0.0


def test_max_drawdown_single_row():
    curve = pd.DataFrame({"cumulative_pnl": [100.0]})
    assert compute_max_drawdown(curve) == 0.0


def test_max_drawdown_uses_compute_equity_curve_output():
    df = pd.DataFrame({
        "trade_date": ["2026-01-01", "2026-01-02", "2026-01-03"],
        "pnl":        [100.0, -80.0, 50.0],
    })
    curve = compute_equity_curve(df)
    # cumulative: 100, 20, 70 → max drawdown = 100-20 = 80
    assert compute_max_drawdown(curve) == pytest.approx(80.0, abs=1e-6)


# ---------------------------------------------------------------------------
# compute_streaks
# ---------------------------------------------------------------------------

def test_streaks_win_streak():
    df = pd.DataFrame({
        "trade_date": ["2026-01-01", "2026-01-02", "2026-01-03"],
        "result":     ["Win",        "Win",        "Win"],
    })
    s = compute_streaks(df)
    assert s["current_streak"] == 3
    assert s["max_win_streak"] == 3
    assert s["max_loss_streak"] == 0
    assert s["streak_type"] == "win"


def test_streaks_loss_streak():
    df = pd.DataFrame({
        "trade_date": ["2026-01-01", "2026-01-02", "2026-01-03"],
        "result":     ["Loss",       "Loss",       "Loss"],
    })
    s = compute_streaks(df)
    assert s["current_streak"] == -3
    assert s["max_win_streak"] == 0
    assert s["max_loss_streak"] == 3
    assert s["streak_type"] == "loss"


def test_streaks_breakeven_resets():
    df = pd.DataFrame({
        "trade_date": ["2026-01-01", "2026-01-02", "2026-01-03"],
        "result":     ["Win",        "Breakeven",  "Win"],
    })
    s = compute_streaks(df)
    assert s["max_win_streak"] == 1   # BE broke the first win before second could stack
    assert s["current_streak"] == 1
    assert s["streak_type"] == "win"


def test_streaks_mixed():
    df = pd.DataFrame({
        "trade_date": ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04", "2026-01-05"],
        "result":     ["Win",        "Win",        "Loss",       "Loss",       "Win"],
    })
    s = compute_streaks(df)
    assert s["max_win_streak"] == 2
    assert s["max_loss_streak"] == 2
    assert s["current_streak"] == 1
    assert s["streak_type"] == "win"


def test_streaks_empty():
    s = compute_streaks(pd.DataFrame())
    assert s == {"current_streak": 0, "max_win_streak": 0, "max_loss_streak": 0, "streak_type": "none"}


def test_streaks_missing_result_column():
    df = pd.DataFrame({"trade_date": ["2026-01-01"], "pnl": [100.0]})
    s = compute_streaks(df)
    assert s["current_streak"] == 0
    assert s["streak_type"] == "none"


def test_streaks_case_insensitive():
    df = pd.DataFrame({
        "trade_date": ["2026-01-01", "2026-01-02"],
        "result":     ["WIN",        "win"],
    })
    s = compute_streaks(df)
    assert s["current_streak"] == 2
    assert s["streak_type"] == "win"


def test_streaks_end_on_breakeven():
    df = pd.DataFrame({
        "trade_date": ["2026-01-01", "2026-01-02", "2026-01-03"],
        "result":     ["Win",        "Win",        "Breakeven"],
    })
    s = compute_streaks(df)
    assert s["max_win_streak"] == 2
    assert s["current_streak"] == 0
    assert s["streak_type"] == "none"


# ---------------------------------------------------------------------------
# compute_breakdown
# ---------------------------------------------------------------------------

def test_breakdown_by_session():
    df = pd.DataFrame({
        "session": ["AM", "AM", "PM", "PM", "AM"],
        "result":  ["Win", "Loss", "Win", "Win", "Win"],
        "pnl":     [200.0, -50.0, 100.0, 150.0, 300.0],
    })
    result = compute_breakdown(df, by="session")

    assert list(result.columns) == ["session", "trades", "wins", "losses", "breakevens",
                                    "win_rate", "avg_pnl", "total_pnl"]
    am = result[result["session"] == "AM"].iloc[0]
    pm = result[result["session"] == "PM"].iloc[0]

    assert am["trades"] == 3
    assert am["wins"] == 2
    assert am["losses"] == 1
    assert am["win_rate"] == pytest.approx(2 / 3, abs=1e-6)

    assert pm["trades"] == 2
    assert pm["wins"] == 2
    assert pm["win_rate"] == pytest.approx(1.0, abs=1e-6)

    # sorted by total_pnl descending
    assert result.iloc[0]["session"] == "AM"   # 450 > 250


def test_breakdown_missing_column():
    df = pd.DataFrame({"session": ["AM"], "pnl": [100.0]})
    result = compute_breakdown(df, by="nonexistent")
    assert result.empty


def test_breakdown_empty_df():
    result = compute_breakdown(pd.DataFrame(), by="session")
    assert result.empty


def test_breakdown_by_asset():
    df = pd.DataFrame({
        "asset":  ["NQ", "NQ", "ES"],
        "result": ["Win", "Loss", "Win"],
        "pnl":    [300.0, -100.0, 50.0],
    })
    result = compute_breakdown(df, by="asset")
    nq = result[result["asset"] == "NQ"].iloc[0]
    assert nq["trades"] == 2
    assert nq["total_pnl"] == pytest.approx(200.0, abs=1e-6)


# ---------------------------------------------------------------------------
# _outcome_masks consistency check
# ---------------------------------------------------------------------------

def test_basic_metrics_uses_result_when_present():
    """When result column is present, win counting uses it — not pnl sign."""
    df = pd.DataFrame({
        "result": ["Win",  "Loss",  "Win"],
        "pnl":    [-50.0,  100.0,   200.0],  # intentionally inverted vs result
    })
    m = compute_basic_metrics(df)
    # result says 2 wins, 1 loss — despite pnl signs being opposite
    assert m["wins"] == 2
    assert m["losses"] == 1
    assert m["win_rate"] == pytest.approx(2 / 3, abs=1e-6)
    # money metrics still use pnl
    assert m["avg_win"] == pytest.approx(75.0, abs=1e-6)   # mean of pnl where result=="Win": (-50+200)/2
    assert m["avg_loss"] == pytest.approx(100.0, abs=1e-6)  # mean of pnl where result=="Loss": 100


def test_basic_metrics_fallback_to_pnl_when_no_result():
    """Original behavior preserved when result column absent."""
    df = pd.DataFrame({
        "trade_date": ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04"],
        "pnl":        [100.0,         200.0,        -50.0,         0.0],
    })
    m = compute_basic_metrics(df)
    assert m["wins"] == 2
    assert m["losses"] == 1
    assert m["win_rate"] == 0.5


# ---------------------------------------------------------------------------
# Week 4 Day 2 — equity_curve_series
# ---------------------------------------------------------------------------

def test_equity_curve_series_simple():
    df = pd.DataFrame({
        "trade_date": ["2026-01-01", "2026-01-02", "2026-01-03"],
        "pnl":        [100.0,        -50.0,         200.0],
    })
    result = equity_curve_series(df)
    assert list(result.columns) == ["trade_date", "pnl", "cumulative_pnl"]
    assert list(result["cumulative_pnl"]) == pytest.approx([100.0, 50.0, 250.0])


def test_equity_curve_series_empty():
    result = equity_curve_series(pd.DataFrame())
    assert result.empty
    assert set(result.columns) == {"trade_date", "pnl", "cumulative_pnl"}


def test_equity_curve_series_is_same_as_compute_equity_curve():
    df = pd.DataFrame({
        "trade_date": ["2026-01-01", "2026-01-02"],
        "pnl":        [50.0, -20.0],
    })
    assert equity_curve_series(df).equals(compute_equity_curve(df))


# ---------------------------------------------------------------------------
# Week 4 Day 2 — daily_pnl
# ---------------------------------------------------------------------------

def test_daily_pnl_aggregates_by_date():
    df = pd.DataFrame({
        "trade_date": ["2026-01-01", "2026-01-01", "2026-01-02"],
        "pnl":        [100.0,        -30.0,         200.0],
    })
    result = daily_pnl(df)
    assert list(result.columns) == ["trade_date", "daily_pnl"]
    assert len(result) == 2
    jan1 = result[result["trade_date"] == "2026-01-01"].iloc[0]
    assert jan1["daily_pnl"] == pytest.approx(70.0)
    jan2 = result[result["trade_date"] == "2026-01-02"].iloc[0]
    assert jan2["daily_pnl"] == pytest.approx(200.0)


def test_daily_pnl_null_trade_date_dropped():
    df = pd.DataFrame({
        "trade_date": ["2026-01-01", None, "2026-01-02"],
        "pnl":        [100.0,        50.0,  200.0],
    })
    result = daily_pnl(df)
    assert len(result) == 2
    assert None not in result["trade_date"].values


def test_daily_pnl_sorted_ascending():
    df = pd.DataFrame({
        "trade_date": ["2026-01-03", "2026-01-01", "2026-01-02"],
        "pnl":        [30.0,         10.0,          20.0],
    })
    result = daily_pnl(df)
    assert list(result["trade_date"]) == ["2026-01-01", "2026-01-02", "2026-01-03"]


def test_daily_pnl_empty_returns_empty():
    result = daily_pnl(pd.DataFrame())
    assert result.empty
    assert set(result.columns) == {"trade_date", "daily_pnl"}


# ---------------------------------------------------------------------------
# Week 4 Day 2 — drawdown_series
# ---------------------------------------------------------------------------

def test_drawdown_series_simple():
    # cumulative: 100, 50, 250
    # running_peak: 100, 100, 250
    # drawdown: 0, -50, 0
    df = pd.DataFrame({
        "trade_date": ["2026-01-01", "2026-01-02", "2026-01-03"],
        "pnl":        [100.0,        -50.0,         200.0],
    })
    result = drawdown_series(df)
    assert list(result.columns) == ["trade_date", "cumulative_pnl", "running_peak", "drawdown"]
    assert list(result["cumulative_pnl"]) == pytest.approx([100.0, 50.0, 250.0])
    assert list(result["running_peak"]) == pytest.approx([100.0, 100.0, 250.0])
    assert list(result["drawdown"]) == pytest.approx([0.0, -50.0, 0.0])


def test_drawdown_series_empty_returns_empty():
    result = drawdown_series(pd.DataFrame())
    assert result.empty
    assert set(result.columns) == {"trade_date", "cumulative_pnl", "running_peak", "drawdown"}


def test_drawdown_series_peak_never_decreases():
    df = pd.DataFrame({
        "trade_date": ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04"],
        "pnl":        [50.0,         -200.0,        100.0,         -30.0],
    })
    result = drawdown_series(df)
    diffs = result["running_peak"].diff().dropna()
    assert (diffs >= 0).all()


def test_drawdown_series_max_matches_compute_max_drawdown():
    df = pd.DataFrame({
        "trade_date": ["2026-01-01", "2026-01-02", "2026-01-03"],
        "pnl":        [100.0,        -80.0,         50.0],
    })
    curve = compute_equity_curve(df)
    expected_max = compute_max_drawdown(curve)
    dd = drawdown_series(df)
    assert abs(dd["drawdown"].min()) == pytest.approx(expected_max, abs=1e-6)


# ---------------------------------------------------------------------------
# Week 4 Day 2 — r_multiple_distribution
# ---------------------------------------------------------------------------

def test_r_multiple_distribution_counts_bins():
    df = pd.DataFrame({
        "rr_realized": [1.0, 1.5, 2.0, -0.5, -1.0, 3.0, 0.5, 2.5],
    })
    result = r_multiple_distribution(df, bins=4)
    assert list(result.columns) == ["bin_left", "bin_right", "count"]
    assert result["count"].sum() == 8  # all non-NaN trades accounted for


def test_r_multiple_distribution_empty_or_all_nan_returns_empty():
    empty_result = r_multiple_distribution(pd.DataFrame())
    assert empty_result.empty
    assert set(empty_result.columns) == {"bin_left", "bin_right", "count"}

    nan_df = pd.DataFrame({"rr_realized": [float("nan"), None]})
    assert r_multiple_distribution(nan_df).empty


def test_r_multiple_distribution_all_same_value():
    df = pd.DataFrame({"rr_realized": [2.0, 2.0, 2.0]})
    result = r_multiple_distribution(df)
    assert len(result) == 1
    assert result["count"].iloc[0] == 3


def test_r_multiple_distribution_nan_excluded():
    df = pd.DataFrame({"rr_realized": [1.0, float("nan"), 2.0, None, 3.0]})
    result = r_multiple_distribution(df, bins=3)
    assert result["count"].sum() == 3  # only 3 non-NaN values


# ---------------------------------------------------------------------------
# Week 4 Day 3 — group-by breakdown helpers
# ---------------------------------------------------------------------------

def test_by_day_of_week_ordering():
    df = pd.DataFrame({
        "day_of_week": ["Friday",  "Tuesday", "Wednesday"],
        "result":      ["Win",     "Loss",    "Win"],
        "pnl":         [100.0,    -50.0,      200.0],
    })
    result = by_day_of_week(df)
    assert list(result["day_of_week"]) == ["Tuesday", "Wednesday", "Friday"]


def test_by_day_of_week_metrics():
    df = pd.DataFrame({
        "day_of_week": ["Monday", "Monday", "Monday"],
        "result":      ["Win",    "Win",    "Loss"],
        "pnl":         [100.0,    200.0,   -50.0],
        "rr_realized": [2.0,      3.0,     -1.0],
    })
    result = by_day_of_week(df)
    assert len(result) == 1
    row = result.iloc[0]
    assert row["trades"] == 3
    assert row["wins"] == 2
    assert row["losses"] == 1
    assert row["win_rate"] == pytest.approx(2 / 3, abs=1e-6)
    assert row["total_pnl"] == pytest.approx(250.0, abs=1e-6)
    assert row["avg_rr_realized"] == pytest.approx(4.0 / 3, abs=1e-6)


def test_by_day_of_week_empty():
    result = by_day_of_week(pd.DataFrame())
    assert result.empty
    assert set(result.columns) == {
        "day_of_week", "trades", "wins", "losses", "breakevens",
        "win_rate", "avg_rr_realized", "total_pnl",
    }


def test_by_session_totals():
    df = pd.DataFrame({
        "session":     ["London", "London", "NY AM"],
        "result":      ["Win",    "Loss",   "Win"],
        "pnl":         [200.0,   -100.0,    150.0],
        "rr_realized": [2.0,      -1.0,     1.5],
    })
    result = by_session(df)
    london = result[result["session"] == "London"].iloc[0]
    assert london["trades"] == 2
    assert london["wins"] == 1
    assert london["losses"] == 1
    assert london["total_pnl"] == pytest.approx(100.0)


def test_by_session_sorted_by_pnl():
    df = pd.DataFrame({
        "session": ["London", "London", "NY AM", "NY AM", "NY AM"],
        "result":  ["Win",    "Win",    "Loss",  "Loss",  "Loss"],
        "pnl":     [500.0,    400.0,   -50.0,  -60.0,   -70.0],
        "rr_realized": [5.0, 4.0, -0.5, -0.6, -0.7],
    })
    result = by_session(df)
    assert result.iloc[0]["session"] == "London"  # 900 > -180


def test_by_strategy_profit_factor():
    df = pd.DataFrame({
        "strategy_used": ["ICT", "ICT", "SMC", "SMC"],
        "result":        ["Win", "Win", "Win", "Loss"],
        "pnl":           [200.0, 300.0, 100.0, -50.0],
    })
    result = by_strategy(df)
    ict = result[result["strategy_used"] == "ICT"].iloc[0]
    smc = result[result["strategy_used"] == "SMC"].iloc[0]
    assert ict["profit_factor"] == float("inf")
    assert smc["profit_factor"] == pytest.approx(2.0, abs=1e-6)


def test_by_strategy_sorted_desc():
    df = pd.DataFrame({
        "strategy_used": ["ICT",   "ICT",   "SMC",  "SMC"],
        "result":        ["Win",   "Loss",  "Loss", "Loss"],
        "pnl":           [100.0, -200.0,  -30.0,  -40.0],
    })
    result = by_strategy(df)
    # SMC total_pnl = -70, ICT total_pnl = -100
    assert result.iloc[0]["strategy_used"] == "SMC"
    assert result.iloc[1]["strategy_used"] == "ICT"


def test_by_strategy_excludes_null_strategy():
    df = pd.DataFrame({
        "strategy_used": ["ICT",  None,   "ICT",  None,    "SMC"],
        "result":        ["Win",  "Win",  "Win",  "Loss",  "Win"],
        "pnl":           [100.0,  999.0,  200.0, -999.0,   50.0],
    })
    result = by_strategy(df)
    assert None not in result["strategy_used"].values
    ict = result[result["strategy_used"] == "ICT"].iloc[0]
    assert ict["trades"] == 2
    assert ict["total_pnl"] == pytest.approx(300.0, abs=1e-6)


def test_by_setup_type_counts():
    df = pd.DataFrame({
        "setup_type": ["OB",  "OB",  "OB",   "FVG", "FVG"],
        "result":     ["Win", "Win", "Loss",  "Win", "Breakeven"],
        "pnl":        [100.0, 200.0, -50.0,  150.0, 0.0],
    })
    result = by_setup_type(df)
    assert list(result.columns) == ["setup_type", "trades", "wins", "losses", "breakevens"]
    ob = result[result["setup_type"] == "OB"].iloc[0]
    fvg = result[result["setup_type"] == "FVG"].iloc[0]
    assert ob["trades"] == 3
    assert ob["wins"] == 2
    assert ob["losses"] == 1
    assert ob["breakevens"] == 0
    assert fvg["wins"] == 1
    assert fvg["breakevens"] == 1


def test_by_setup_type_sorted_by_trades():
    df = pd.DataFrame({
        "setup_type": ["FVG", "OB",  "OB",  "OB"],
        "result":     ["Win", "Win", "Win", "Loss"],
        "pnl":        [100.0, 50.0,  60.0, -10.0],
    })
    result = by_setup_type(df)
    assert result.iloc[0]["setup_type"] == "OB"  # 3 trades > 1 trade


def test_emotion_vs_rr_avg():
    df = pd.DataFrame({
        "emotions_before": ["Calm",  "Calm",  "Fearful"],
        "rr_realized":     [2.0,     4.0,     -1.0],
    })
    result = emotion_vs_rr(df)
    assert list(result.columns) == ["emotions_before", "trades", "avg_rr_realized"]
    calm = result[result["emotions_before"] == "Calm"].iloc[0]
    assert calm["trades"] == 2
    assert calm["avg_rr_realized"] == pytest.approx(3.0, abs=1e-6)


def test_emotion_vs_rr_nan_excluded():
    df = pd.DataFrame({
        "emotions_before": ["Calm", "Calm",         "Calm"],
        "rr_realized":     [2.0,   float("nan"),    4.0],
    })
    result = emotion_vs_rr(df)
    calm = result[result["emotions_before"] == "Calm"].iloc[0]
    assert calm["trades"] == 3                                  # all 3 rows counted
    assert calm["avg_rr_realized"] == pytest.approx(3.0, abs=1e-6)  # NaN excluded from mean


def test_by_hour_of_day_present():
    df = pd.DataFrame({
        "hour_of_day": [9,     9,     10,    14],
        "pnl":         [100.0, 200.0, -50.0, 150.0],
        "rr_realized": [2.0,   3.0,   -1.0,  1.5],
    })
    result = by_hour_of_day(df)
    assert list(result.columns) == ["hour_of_day", "trades", "total_pnl", "avg_rr_realized"]
    assert list(result["hour_of_day"]) == [9, 10, 14]
    h9 = result[result["hour_of_day"] == 9].iloc[0]
    assert h9["trades"] == 2
    assert h9["total_pnl"] == pytest.approx(300.0, abs=1e-6)
    assert h9["avg_rr_realized"] == pytest.approx(2.5, abs=1e-6)


def test_by_hour_of_day_missing_column():
    df = pd.DataFrame({
        "trade_date": ["2026-01-01"],
        "pnl":        [100.0],
    })
    result = by_hour_of_day(df)
    assert result.empty
    assert set(result.columns) == {"hour_of_day", "trades", "total_pnl", "avg_rr_realized"}


def test_by_asset_empty():
    result = by_asset(pd.DataFrame())
    assert result.empty
    assert set(result.columns) == {
        "asset", "trades", "wins", "losses", "breakevens",
        "win_rate", "total_pnl", "profit_factor",
    }


# ---------------------------------------------------------------------------
# Phase 2 — killzone analytics + calendar
# ---------------------------------------------------------------------------

_KZ_DF = pd.DataFrame({
    "killzone":    ["ny_am", "ny_am", "london_open", "asia"],
    "result":      ["Win", "Loss", "Win", "Loss"],
    "pnl":         [300.0, -100.0, 200.0, -50.0],
    "rr_realized": [3.0, -1.0, 2.0, -1.0],
})


def test_killzone_performance_known_values():
    res = killzone_performance(_KZ_DF)
    by_kz = {row["killzone"]: row for _, row in res.iterrows()}

    ny = by_kz["ny_am"]
    assert ny["trades"] == 2
    assert ny["win_rate"] == pytest.approx(0.5)
    assert ny["avg_rr_realized"] == pytest.approx(1.0)   # (3 + -1)/2
    assert ny["total_pnl"] == pytest.approx(200.0)
    assert ny["profit_factor"] == pytest.approx(3.0)     # 300/100

    lo = by_kz["london_open"]
    assert lo["profit_factor"] == float("inf")           # win, no losses
    assert lo["avg_rr_realized"] == pytest.approx(2.0)

    asia = by_kz["asia"]
    assert asia["total_pnl"] == pytest.approx(-50.0)
    assert asia["profit_factor"] == 0.0                  # only losses


def test_killzone_performance_chronological_order():
    res = killzone_performance(_KZ_DF)
    # asia < london_open < ny_am regardless of input/pnl order
    assert list(res["killzone"]) == ["asia", "london_open", "ny_am"]


def test_killzone_performance_empty():
    res = killzone_performance(pd.DataFrame())
    assert res.empty
    assert "killzone" in res.columns and "profit_factor" in res.columns


def test_killzone_performance_excludes_null_killzone():
    df = pd.DataFrame({"killzone": [None, "ny_am"], "result": ["Win", "Win"], "pnl": [10.0, 20.0]})
    res = killzone_performance(df)
    assert list(res["killzone"]) == ["ny_am"]


def test_confirmation_model_performance_known_values():
    df = pd.DataFrame({
        "confirmation_model": ["BOS", "BOS", "FVG Fill"],
        "result": ["Win", "Loss", "Win"],
        "pnl":    [100.0, -50.0, 80.0],
    })
    res = confirmation_model_performance(df)
    by_cm = {row["confirmation_model"]: row for _, row in res.iterrows()}
    assert by_cm["BOS"]["trades"] == 2
    assert by_cm["BOS"]["profit_factor"] == pytest.approx(2.0)   # 100/50
    assert by_cm["FVG Fill"]["profit_factor"] == float("inf")
    # sorted by total_pnl desc → FVG Fill (80) before BOS (50)
    assert list(res["confirmation_model"]) == ["FVG Fill", "BOS"]


def test_mistake_frequency_counts_and_pnl():
    df = pd.DataFrame({
        "mistake_tags": ['["FOMO", "Late Entry"]', '["FOMO"]', None, "[]"],
        "pnl":          [-100.0, -50.0, 200.0, 10.0],
    })
    res = mistake_frequency(df)
    by_tag = {row["mistake_tag"]: row for _, row in res.iterrows()}
    assert by_tag["FOMO"]["count"] == 2
    assert by_tag["FOMO"]["total_pnl"] == pytest.approx(-150.0)
    assert by_tag["FOMO"]["avg_pnl"] == pytest.approx(-75.0)
    assert by_tag["Late Entry"]["count"] == 1
    # sorted by count desc → FOMO first
    assert res.iloc[0]["mistake_tag"] == "FOMO"


def test_mistake_frequency_handles_malformed_and_empty():
    df = pd.DataFrame({"mistake_tags": ["not json", None, ""], "pnl": [1.0, 2.0, 3.0]})
    res = mistake_frequency(df)
    assert res.empty
    assert set(res.columns) == {"mistake_tag", "count", "total_pnl", "avg_pnl"}


def test_calendar_daily_pnl_known_values():
    df = pd.DataFrame({
        "trade_date": ["2025-01-15", "2025-01-15", "2025-01-20", "2025-02-01"],
        "result":     ["Win", "Loss", "Win", "Win"],
        "pnl":        [300.0, -100.0, 50.0, 999.0],
    })
    res = calendar_daily_pnl(df, 2025, 1)
    by_day = {int(row["day"]): row for _, row in res.iterrows()}
    assert set(by_day.keys()) == {15, 20}            # Feb trade excluded
    assert by_day[15]["net_pnl"] == pytest.approx(200.0)
    assert by_day[15]["trades"] == 2
    assert by_day[15]["wins"] == 1
    assert by_day[15]["losses"] == 1
    assert by_day[20]["net_pnl"] == pytest.approx(50.0)


def test_calendar_daily_pnl_empty_month():
    df = pd.DataFrame({
        "trade_date": ["2025-03-01"],
        "result": ["Win"],
        "pnl": [100.0],
    })
    res = calendar_daily_pnl(df, 2025, 1)   # January has no trades
    assert res.empty
    assert set(res.columns) == {"trade_date", "day", "net_pnl", "trades", "wins", "losses"}


def test_calendar_daily_pnl_single_trade():
    df = pd.DataFrame({"trade_date": ["2025-01-07"], "result": ["Loss"], "pnl": [-25.0]})
    res = calendar_daily_pnl(df, 2025, 1)
    assert len(res) == 1
    assert int(res.iloc[0]["day"]) == 7
    assert res.iloc[0]["net_pnl"] == pytest.approx(-25.0)


# ---------------------------------------------------------------------------
# total_edge_leak (Week 5 Phase 3)
# ---------------------------------------------------------------------------

def test_total_edge_leak_known_values():
    """Sum P&L over trades that broke rules (followed_rules==0) OR carry mistake tags."""
    from src.tradelens.services.metrics import total_edge_leak

    df = pd.DataFrame({
        "followed_rules": [1, 0, 1, 0, None],
        "mistake_tags":   ["[]", "[]", '["FOMO"]', '["Late Entry"]', None],
        "pnl":            [200.0, -100.0, -50.0, -30.0, 999.0],
    })
    # clean(+200) excluded; -100 (broke rules) + -50 (mistake) + -30 (both, once) = -180
    assert total_edge_leak(df) == pytest.approx(-180.0)


def test_total_edge_leak_counts_each_trade_once():
    """A trade that both broke rules AND has a mistake tag is counted a single time."""
    from src.tradelens.services.metrics import total_edge_leak

    df = pd.DataFrame({
        "followed_rules": [0],
        "mistake_tags":   ['["FOMO", "Oversize"]'],
        "pnl":            [-40.0],
    })
    assert total_edge_leak(df) == pytest.approx(-40.0)


def test_total_edge_leak_clean_trades_are_zero():
    """All trades followed rules and carry no mistake tags → no leak."""
    from src.tradelens.services.metrics import total_edge_leak

    df = pd.DataFrame({
        "followed_rules": [1, 1, 1],
        "mistake_tags":   ["[]", None, ""],
        "pnl":            [100.0, -20.0, 50.0],
    })
    assert total_edge_leak(df) == pytest.approx(0.0)


def test_total_edge_leak_preserves_sign_for_lucky_breaks():
    """Rule-breaking trades that happened to win keep their positive sign."""
    from src.tradelens.services.metrics import total_edge_leak

    df = pd.DataFrame({
        "followed_rules": [0, 1],
        "mistake_tags":   ["[]", "[]"],
        "pnl":            [300.0, 100.0],
    })
    assert total_edge_leak(df) == pytest.approx(300.0)


def test_total_edge_leak_empty_returns_zero():
    from src.tradelens.services.metrics import total_edge_leak

    assert total_edge_leak(pd.DataFrame()) == pytest.approx(0.0)


def test_total_edge_leak_missing_signal_columns_returns_zero():
    """Without followed_rules or mistake_tags there is no leak signal."""
    from src.tradelens.services.metrics import total_edge_leak

    df = pd.DataFrame({"pnl": [100.0, -50.0]})
    assert total_edge_leak(df) == pytest.approx(0.0)
