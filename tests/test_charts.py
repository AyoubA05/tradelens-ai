"""
Render tests for every Plotly chart (Phase 5, week6-d5, flow-pass §d).

Each chart must return a plotly Figure on populated input AND on empty input,
never raising. Inputs are produced through the real metrics pipeline so the
shapes match what the pages pass.
"""

import pandas as pd
import plotly.graph_objects as go

from src.tradelens.services.demo import get_demo_df
from src.tradelens.services.metrics import (
    by_day_of_week,
    by_setup_type,
    by_strategy,
    calendar_daily_pnl,
    compute_profit_factor_raw,
    drawdown_series,
    emotion_vs_rr,
    equity_curve_series,
    r_multiple_distribution,
)
from src.tradelens.ui.components.charts import (
    calendar_heatmap_chart,
    drawdown_chart,
    emotion_vs_rr_chart,
    equity_curve_chart,
    pnl_by_strategy_chart,
    profit_factor_gauge,
    r_multiple_histogram,
    setup_breakdown_chart,
    win_rate_by_dow_chart,
)

_DF = get_demo_df()
_EMPTY = pd.DataFrame()


def _is_fig(obj):
    assert isinstance(obj, go.Figure)


# --- Populated inputs ---------------------------------------------------------


def test_equity_curve_chart_renders():
    _is_fig(equity_curve_chart(equity_curve_series(_DF)))


def test_drawdown_chart_renders():
    _is_fig(drawdown_chart(drawdown_series(_DF)))


def test_win_rate_by_dow_chart_renders():
    _is_fig(win_rate_by_dow_chart(by_day_of_week(_DF)))


def test_pnl_by_strategy_chart_renders():
    _is_fig(pnl_by_strategy_chart(by_strategy(_DF)))


def test_profit_factor_gauge_renders():
    _is_fig(profit_factor_gauge(compute_profit_factor_raw(_DF)))


def test_profit_factor_gauge_handles_inf():
    _is_fig(profit_factor_gauge(float("inf")))


def test_r_multiple_histogram_renders():
    _is_fig(r_multiple_histogram(r_multiple_distribution(_DF), median_rr=1.5))


def test_emotion_vs_rr_chart_renders():
    _is_fig(emotion_vs_rr_chart(emotion_vs_rr(_DF)))


def test_setup_breakdown_chart_renders():
    _is_fig(setup_breakdown_chart(by_setup_type(_DF)))


def test_calendar_heatmap_chart_renders():
    _is_fig(calendar_heatmap_chart(calendar_daily_pnl(_DF, 2026, 6), 2026, 6))


# --- Empty inputs (designed empty figure, never an exception) ------------------


def test_all_charts_handle_empty_input():
    _is_fig(equity_curve_chart(_EMPTY))
    _is_fig(drawdown_chart(_EMPTY))
    _is_fig(win_rate_by_dow_chart(_EMPTY))
    _is_fig(pnl_by_strategy_chart(_EMPTY))
    _is_fig(profit_factor_gauge(0.0))
    _is_fig(r_multiple_histogram(_EMPTY, median_rr=None))
    _is_fig(emotion_vs_rr_chart(_EMPTY))
    _is_fig(setup_breakdown_chart(_EMPTY))
    _is_fig(calendar_heatmap_chart(calendar_daily_pnl(_EMPTY, 2026, 1), 2026, 1))
