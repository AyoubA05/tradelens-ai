"""Thresholds that decide when a chart is worth drawing.

A single dramatic bar or a two-point "curve" reads as a finding when it is
really just a small sample, so these rules are shared by every analytical
surface rather than re-decided per page.
"""

import pandas as pd
import pytest

from src.tradelens.ui.components.data_state import enough_categories, sample_state


def test_no_trades_shows_nothing():
    state = sample_state(pd.DataFrame())
    assert not state.show_summary
    assert not state.show_series
    assert not state.show_comparisons
    assert not state.show_patterns


def test_none_is_treated_as_no_trades():
    assert sample_state(None).trades == 0


def test_one_trade_allows_summary_but_not_series_or_comparisons():
    state = sample_state(pd.DataFrame({"trade_date": ["2026-07-18"], "pnl": [-500]}))
    assert state.show_summary
    assert not state.show_series
    assert not state.show_comparisons


def test_two_dated_trades_allow_series():
    df = pd.DataFrame({"trade_date": ["2026-07-17", "2026-07-18"], "pnl": [100, -50]})
    assert sample_state(df).show_series


def test_two_trades_on_one_date_are_not_a_series():
    """Two points at the same x are a dot, not a curve."""
    df = pd.DataFrame({"trade_date": ["2026-07-18", "2026-07-18"], "pnl": [100, -50]})
    state = sample_state(df)
    assert not state.show_series
    assert state.show_comparisons


def test_five_trades_allow_pattern_sections():
    df = pd.DataFrame({"trade_date": [f"2026-07-{d:02d}" for d in range(1, 6)]})
    assert sample_state(df).show_patterns


def test_four_trades_do_not_allow_pattern_sections():
    df = pd.DataFrame({"trade_date": [f"2026-07-{d:02d}" for d in range(1, 5)]})
    assert not sample_state(df).show_patterns


def test_unparseable_dates_do_not_count_as_points():
    df = pd.DataFrame({"trade_date": ["not-a-date", "also-bad"], "pnl": [1, 2]})
    state = sample_state(df)
    assert state.dated_points == 0
    assert not state.show_series


def test_missing_trade_date_column_is_safe():
    state = sample_state(pd.DataFrame({"pnl": [1, 2]}))
    assert state.dated_points == 0
    assert not state.show_series
    assert state.show_comparisons


# ---------------------------------------------------------------------------
# enough_categories — a bar chart needs something to compare against
# ---------------------------------------------------------------------------


def test_one_category_is_not_a_comparison():
    df = pd.DataFrame({"session": ["London"], "total_pnl": [-500]})
    assert not enough_categories(df, "session")


def test_two_categories_are_a_comparison():
    df = pd.DataFrame({"session": ["London", "NY"], "total_pnl": [-500, 250]})
    assert enough_categories(df, "session")


def test_empty_or_missing_column_is_not_a_comparison():
    assert not enough_categories(pd.DataFrame(), "session")
    assert not enough_categories(pd.DataFrame({"other": [1, 2]}), "session")


def test_repeated_category_is_not_a_comparison():
    df = pd.DataFrame({"session": ["London", "London"], "total_pnl": [-500, 250]})
    assert not enough_categories(df, "session")


def test_blank_categories_are_ignored():
    df = pd.DataFrame({"session": ["London", None], "total_pnl": [-500, 250]})
    assert not enough_categories(df, "session")


# ---------------------------------------------------------------------------
# End-to-end: a one-trade dashboard must not draw a chart
# ---------------------------------------------------------------------------

import os  # noqa: E402
import subprocess  # noqa: E402
import sys  # noqa: E402
from pathlib import Path  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
RUNNER = ROOT / "tests" / "app_boot_check.py"
APP = ROOT / "src" / "tradelens" / "ui" / "app.py"


def _boot(app_path, marker, seed, tmp_path):
    env = dict(os.environ)
    env["DATABASE_URL"] = f"sqlite:///{tmp_path / 'ds.db'}"
    env["DEMO_MODE"] = "true"
    return subprocess.run(
        [sys.executable, str(RUNNER), str(ROOT), str(app_path), marker, seed],
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )


def test_dashboard_with_one_trade_draws_no_chart(tmp_path):
    """One trade earns KPIs and an explanation — never an equity curve.

    The marker copy changed with the Overview redesign: the dominant chart
    now needs four dated points, not two, so the old "Two trading dates are
    needed" wording would state a threshold the page no longer applies. The
    behaviour under test is unchanged.
    """
    proc = _boot(
        APP,
        "no-charts:will unlock the equity curve",
        "one",
        tmp_path,
    )
    assert proc.returncode == 0, f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"


def test_dashboard_with_two_dated_trades_draws_the_curve(tmp_path):
    """The same page still charts as soon as the sample supports it."""
    proc = _boot(APP, "-", "1", tmp_path)
    assert proc.returncode == 0, f"STDOUT:\n{proc.stdout}\nSTDERR:\n{proc.stderr}"


def test_analytics_does_not_report_a_losing_largest_win():
    """best_trade is the max of the P&L column, so an all-losing sample
    would otherwise show 'Largest Win: -$500.00'."""
    src = (ROOT / "src" / "tradelens" / "ui" / "pages" / "4_Analytics.py").read_text(
        encoding="utf-8"
    )
    assert 'if m["wins"] else "—"' in src
    assert 'if m["losses"] else "—"' in src


# ---------------------------------------------------------------------------
# Task 5 — the shared date-series policy (spec §5.4a)
# ---------------------------------------------------------------------------
from src.tradelens.ui.components.data_state import (  # noqa: E402
    MIN_DATED_POINTS,
    show_dated_instrument,
)


def test_a_dated_instrument_needs_four_populated_trading_days():
    """Spec §5.4a. One rule for the equity curve and the calendar heatmap."""
    assert MIN_DATED_POINTS == 4


def test_two_trades_on_one_date_are_one_populated_trading_day():
    df = pd.DataFrame(
        {"trade_date": ["2026-08-01", "2026-08-01", "2026-08-02"], "pnl": [1, 2, 3]}
    )
    assert sample_state(df).dated_points == 2
    assert show_dated_instrument(sample_state(df)) is False


def test_four_populated_days_unlock_the_dated_instruments():
    dates = ["2026-08-01", "2026-08-02", "2026-08-03", "2026-08-04"]
    df = pd.DataFrame({"trade_date": dates, "pnl": [1, 2, 3, 4]})
    assert show_dated_instrument(sample_state(df)) is True


@pytest.mark.parametrize("days", range(0, 9))
def test_the_shared_gate_agrees_with_the_existing_dominant_series_gate(days):
    """Extending one constant, not inventing a threshold: every populated day
    carries at least one trade, so dated >= 4 already implies trades >= 4."""
    dates = [f"2026-08-{d + 1:02d}" for d in range(days)]
    df = pd.DataFrame({"trade_date": dates, "pnl": [1.0] * days})
    state = sample_state(df)
    assert show_dated_instrument(state) == state.show_dominant_series
