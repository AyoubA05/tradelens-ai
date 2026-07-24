"""One low-data policy shared by every analytical surface.

Plotly will happily draw a full-height bar for a single trade and a
straight line between two points. Both read as a finding when they are
really just a small sample, which is the fastest way to lose a trader's
trust in the analytics. These rules decide what a sample has earned the
right to display, so the answer is the same on the Dashboard and the
Analytics page.

The decision functions are pure and Streamlit-free; only the render
helper touches Streamlit.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

# A curve needs two distinct x values; a comparison needs two things to
# compare; behavioural patterns need enough rows that one session isn't
# the whole story.
_MIN_SERIES_POINTS = 2
_MIN_COMPARISON_TRADES = 2
_MIN_CATEGORIES = 2
_MIN_PATTERN_TRADES = 5


@dataclass(frozen=True)
class SampleState:
    """What a given sample of trades has earned the right to display."""

    trades: int
    dated_points: int
    show_summary: bool
    show_series: bool
    show_comparisons: bool
    show_patterns: bool


def sample_state(df: pd.DataFrame | None) -> SampleState:
    """Classify a trade DataFrame against the shared display thresholds."""
    trades = 0 if df is None or df.empty else len(df)

    dated = 0
    if trades and "trade_date" in df.columns:
        # trade_date is an ISO "YYYY-MM-DD" string by schema; naming the
        # format keeps pandas off its per-element dateutil fallback.
        parsed = pd.to_datetime(df["trade_date"], errors="coerce", format="ISO8601")
        dated = int(parsed.dropna().nunique())

    return SampleState(
        trades=trades,
        dated_points=dated,
        show_summary=trades >= 1,
        show_series=trades >= _MIN_SERIES_POINTS and dated >= _MIN_SERIES_POINTS,
        show_comparisons=trades >= _MIN_COMPARISON_TRADES,
        show_patterns=trades >= _MIN_PATTERN_TRADES,
    )


def enough_categories(
    df: pd.DataFrame | None, column: str, minimum: int = _MIN_CATEGORIES
) -> bool:
    """True when a breakdown has enough distinct categories to compare.

    A one-bar "P&L by Session" chart states nothing that its own label
    doesn't already say.
    """
    if df is None or df.empty or column not in df.columns:
        return False
    return int(df[column].dropna().nunique()) >= minimum


def render_data_state(title: str, body: str, icon: str = "◆") -> None:
    """Render the shared low-data explanation in place of a chart.

    Deliberately compact: an explanation should not occupy the canvas the
    withheld chart would have.
    """
    import streamlit as st

    from src.tradelens.ui.design_system import render_empty_state

    st.markdown(
        f'<div class="tl-data-state">{render_empty_state(icon, title, body)}</div>',
        unsafe_allow_html=True,
    )


def trades_needed(state: SampleState, threshold: int) -> int:
    """How many more trades until a threshold unlocks (never negative)."""
    return max(0, threshold - state.trades)
