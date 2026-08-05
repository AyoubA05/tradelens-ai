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

# A *dominant* instrument makes a stronger claim than a chart tucked into an
# analytics grid: it is the largest thing on the page, so it reads as the
# headline finding. Two points can honestly draw a line, but giving that line
# half the Overview states a trend the sample has not earned. Four points is
# where a shape starts to exist (spec 11.1).
_MIN_DOMINANT_POINTS = 4

# Spec 5.4a. One rule governs every dated instrument — the equity curve and
# the calendar heatmap alike. This is not a new threshold: it is the existing
# dominant-series constant, exposed publicly so the heatmap cannot drift onto
# a second one.
#
# The generic "fewer than 20 cells" heatmap heuristic does NOT transfer. It
# assumes every cell samples a continuous variable, so an unfilled cell is
# missing data. In a trading calendar an empty day means no trade was taken,
# which is information — a sparse month is a truthful picture of a sparse
# month. What four populated days protects against is narrower: a grid with
# too few days to show any weekday or clustering pattern at all.
MIN_DATED_POINTS = _MIN_DOMINANT_POINTS


def show_dated_instrument(state: SampleState) -> bool:
    """Whether a dated instrument has earned the right to draw.

    Populated trading days, not trades: two trades on one date are one day.
    Every populated day carries at least one trade, so `dated >= 4` already
    implies `trades >= 4` — which is why this agrees with show_dominant_series
    on every sample, pinned by a parametrised test rather than assumed.
    """
    return state.dated_points >= MIN_DATED_POINTS


@dataclass(frozen=True)
class SampleState:
    """What a given sample of trades has earned the right to display."""

    trades: int
    dated_points: int
    show_summary: bool
    show_series: bool
    show_dominant_series: bool
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
        show_dominant_series=(
            trades >= _MIN_DOMINANT_POINTS and dated >= _MIN_DOMINANT_POINTS
        ),
        show_comparisons=trades >= _MIN_COMPARISON_TRADES,
        show_patterns=trades >= _MIN_PATTERN_TRADES,
    )


@dataclass(frozen=True)
class LeadingCategory:
    """The category carrying the most of some value, with its own context.

    Deliberately copy-free: this decides *what is true* about a sample, and
    the calling surface decides how to say it. Returning the share and the
    category count is what lets a caller state a limitation honestly rather
    than presenting one session as if it had been compared against others.
    """

    key: str
    total: float
    count: int
    overall_total: float
    categories: int

    @property
    def share(self) -> float:
        """Fraction of the overall total this category carried (0.0 when the
        overall total is zero — a share of nothing is not a majority)."""
        if not self.overall_total:
            return 0.0
        return self.total / self.overall_total

    @property
    def is_only_category(self) -> bool:
        return self.categories <= 1


def leading_category(
    df: pd.DataFrame | None,
    column: str,
    value_column: str = "pnl",
) -> LeadingCategory | None:
    """The category with the highest summed value, or None when unearned.

    Returns None below the pattern threshold: naming a "leading" session out
    of three trades describes noise, and doing it in an editorial voice is
    how an interface starts overstating what the journal knows.
    """
    state = sample_state(df)
    if not state.show_patterns:
        return None
    if df is None or column not in df.columns or value_column not in df.columns:
        return None

    scoped = df[df[column].notna() & (df[column].astype(str).str.strip() != "")]
    scoped = scoped[scoped[value_column].notna()]
    if scoped.empty:
        return None

    grouped = scoped.groupby(scoped[column].astype(str))[value_column].agg(
        ["sum", "count"]
    )
    if grouped.empty:
        return None

    key = str(grouped["sum"].idxmax())
    return LeadingCategory(
        key=key,
        total=float(grouped.loc[key, "sum"]),
        count=int(grouped.loc[key, "count"]),
        overall_total=float(grouped["sum"].sum()),
        categories=int(len(grouped)),
    )


def has_variation(values, minimum_distinct: int = 2) -> bool:
    """True when a column actually varies enough to plot over time.

    A "risk per trade" line through one repeated value is a flat rule drawn
    at full height, which reads as a finding about behaviour rather than as
    the constant it is. Same idea as ``enough_categories``, for a numeric
    series rather than a breakdown.
    """
    if values is None:
        return False
    series = pd.Series(values)
    if series.empty:
        return False
    return int(pd.to_numeric(series, errors="coerce").dropna().nunique()) >= (
        minimum_distinct
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


def render_data_state(title: str, body: str, icon: str = "insights") -> None:
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
