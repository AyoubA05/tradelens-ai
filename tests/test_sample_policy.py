"""The low-data policy, now shared by Streamlit and the API.

These thresholds are not arbitrary: a full-height bar for one trade and a
straight line between two points both read as findings when they are really a
small sample, which is the fastest way to lose a trader's trust.
"""

import pandas as pd
import pytest

from src.tradelens.services.sample_policy import (
    MIN_DATED_POINTS,
    SampleState,
    sample_state,
    trades_needed,
)


def _df(n, dated=None):
    """n trades; `dated` distinct trade dates (defaults to n)."""
    dates = [f"2026-08-{(i % (dated or n)) + 1:02d}" for i in range(n)]
    return pd.DataFrame({"trade_date": dates, "pnl": [10.0] * n})


def test_no_trades_earns_nothing():
    s = sample_state(pd.DataFrame())
    assert s.trades == 0
    assert not s.show_summary
    assert not s.show_series
    assert not s.show_comparisons


def test_one_trade_earns_a_summary_but_no_curve():
    s = sample_state(_df(1))
    assert s.show_summary
    assert not s.show_series, "two points are the minimum for a line"


def test_two_dated_points_earn_a_series_but_not_a_dominant_one():
    s = sample_state(_df(2))
    assert s.show_series
    assert not s.show_dominant_series, "a headline instrument needs four points"


def test_four_dated_points_earn_the_dominant_series():
    assert sample_state(_df(4)).show_dominant_series
    assert MIN_DATED_POINTS == 4


def test_patterns_need_five_trades():
    assert not sample_state(_df(4)).show_patterns
    assert sample_state(_df(5)).show_patterns


def test_dated_points_counts_distinct_days_not_rows():
    # Ten trades on two days is still two points on a curve.
    s = sample_state(_df(10, dated=2))
    assert s.trades == 10
    assert s.dated_points == 2
    assert not s.show_dominant_series


def test_none_is_treated_as_empty():
    assert sample_state(None).trades == 0


@pytest.mark.parametrize(
    "have,threshold,want", [(0, 5, 5), (3, 5, 2), (5, 5, 0), (7, 5, 0)]
)
def test_trades_needed_never_goes_negative(have, threshold, want):
    assert (
        trades_needed(
            sample_state(_df(have)) if have else sample_state(None), threshold
        )
        == want
    )


def test_the_streamlit_component_re_exports_the_same_objects():
    """Streamlit must keep working during parity, on the same policy.

    Two copies of this policy would let the Dashboard and the API disagree about
    what a sample has earned — the exact thing its docstring forbids.
    """
    from src.tradelens.ui.components import data_state

    assert data_state.sample_state is sample_state
    assert data_state.SampleState is SampleState
    assert data_state.MIN_DATED_POINTS == MIN_DATED_POINTS
