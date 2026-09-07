"""The analytics payload: one owner, one period, one filtered sample.

Pure projection. Every figure comes from `services/metrics`, which is
parity-pinned — this module reads those functions and shapes their output for
the wire, and computes nothing of its own. A formula that existed here as
well as there would be a second implementation, and the two would diverge
the first time either changed.

The one rule everything else follows: **an undefined figure stays
undefined.** `0.0` means a trader measured zero. `null` with a state means we
could not measure. Phase 2 shipped a plan that would have rendered five
undefined figures as `$0.00` and told a four-trade trader their consistency
was "0 out of 100"; the shape below is what stops that being expressible.

No Streamlit imports here.
"""

from __future__ import annotations

from typing import Any, Dict, List

import pandas as pd

from src.tradelens.api.serialization import finite_or_state
from src.tradelens.services.metrics import (
    compute_basic_metrics,
    compute_equity_curve,
    compute_expectancy,
    compute_max_drawdown,
    compute_profit_factor_raw,
    compute_streaks,
    daily_pnl,
    drawdown_series,
    r_multiple_distribution,
)
from src.tradelens.services.sample_policy import _MIN_SERIES_POINTS

_UNDEFINED_NO_SAMPLE = {"value": None, "state": "undefined_no_sample"}


def pair(value: Any) -> Dict[str, Any]:
    """A possibly-undefined number as `{value, state}`."""
    number, state = finite_or_state(value)
    if number is None and state is None:
        state = "undefined_no_sample"
    return {"value": number, "state": state}


def undefined(state: str) -> Dict[str, Any]:
    return {"value": None, "state": state}


def money_pair(value: Any, *, complete: bool) -> Dict[str, Any]:
    """A monetary figure that is only meaningful when its rows record P&L.

    A journal kept for the process — entries, stops, notes — with the P&L
    column left blank has not earned a total of $0.00. It has no total.
    """
    if not complete:
        return undefined("undefined_incomplete_sample")
    return pair(value)


def sample_pair(value: Any, insufficient: bool) -> Dict[str, Any]:
    """A number gated by sample size, not merely by non-finiteness.

    `finite_or_state` only recovers a state from NaN/±inf. Several metrics
    flatten "not enough data" into an ordinary finite 0.0 — max drawdown
    below two points, consistency below five trades, an average over zero
    members, a win rate over zero trades — so `pair` alone is a no-op on all
    of them and 0.0 would read as a real answer. `insufficient` is computed
    by the caller from sample counts it already holds, never from the
    metric's return value.
    """
    if insufficient:
        return dict(_UNDEFINED_NO_SAMPLE)
    return pair(value)


def need(mapping: Any, key: str) -> Any:
    """Read a required key, loudly.

    Deliberately not `.get(key, 0.0)`. If a metric is renamed or its output
    reshaped, a defaulting read turns that mistake into a plausible $0.00 on
    a trader's screen instead of a failing test.
    """
    if key not in mapping:
        raise KeyError("metric output has no key {!r}".format(key))
    return mapping[key]


_COLUMNS = (
    "id",
    "trade_date",
    "asset",
    "direction",
    "timeframe",
    "session",
    "killzone",
    "setup_type",
    "confirmation_model",
    "strategy_used",
    "htf_bias",
    "result",
    "pnl",
    "rr_planned",
    "rr_realized",
    "risk_amount",
    "position_size",
    "entry_time",
    "day_of_week",
    "followed_rules",
    "mistake_tags",
    "emotions_before",
    "emotions_during",
    "emotions_after",
    "ai_grade",
    "user_grade",
)


def frame(trades: List[Any]) -> pd.DataFrame:
    """ORM rows as the DataFrame `services/metrics` expects.

    An empty list yields an empty frame, never a single row of zeroes: the
    metric functions already know how to answer "no sample", and inventing a
    row here would answer it wrongly.
    """
    if not trades:
        return pd.DataFrame()
    return pd.DataFrame([_row(trade) for trade in trades])


def _row(trade: Any) -> Dict[str, Any]:
    return {column: getattr(trade, column, None) for column in _COLUMNS}


# Below this many rows a drawdown is not a measurement. `sample_policy` owns
# the number; naming it here rather than writing `2` keeps the two surfaces
# agreeing about what a sample has earned.
MIN_DRAWDOWN_POINTS = _MIN_SERIES_POINTS


def pnl_is_complete(df: pd.DataFrame) -> bool:
    """Whether every row in this sample records a P&L.

    Not "some rows have P&L". A total over a sample where half the rows are
    blank is a number with no meaning: it is neither the trader's real
    result nor a subset they chose.
    """
    if df.empty or "pnl" not in df.columns:
        return False
    return bool(df["pnl"].notna().all())


def insufficient_for(df: pd.DataFrame, minimum: int) -> bool:
    """Whether this sample is too small for a figure that needs `minimum` rows."""
    return len(df) < minimum


def build_performance(df: pd.DataFrame) -> Dict[str, Any]:
    """Lens 1 — how did this period actually go?"""
    if df.empty:
        return {
            "total_pnl": undefined("undefined_no_sample"),
            "win_rate": dict(_UNDEFINED_NO_SAMPLE),
            "expectancy": dict(_UNDEFINED_NO_SAMPLE),
            "profit_factor": dict(_UNDEFINED_NO_SAMPLE),
            "total_trades": 0,
            "equity_curve": [],
            "daily_pnl": [],
            "streaks": {
                "current": dict(_UNDEFINED_NO_SAMPLE),
                "max_win": dict(_UNDEFINED_NO_SAMPLE),
                "max_loss": dict(_UNDEFINED_NO_SAMPLE),
            },
        }

    basic = compute_basic_metrics(df)
    complete = pnl_is_complete(df)
    total = len(df)
    streaks = compute_streaks(df)

    return {
        # `need`, not `.get`: a renamed metric key must fail a test, not
        # render as a plausible $0.00.
        "total_pnl": money_pair(need(basic, "total_pnl"), complete=complete),
        "win_rate": sample_pair(need(basic, "win_rate"), insufficient_for(df, 1)),
        "expectancy": money_pair(compute_expectancy(basic), complete=complete),
        "profit_factor": pair(compute_profit_factor_raw(df)),
        "total_trades": total,
        # VERIFIED column names. `compute_equity_curve` emits
        # `trade_date/pnl/cumulative_pnl` and `daily_pnl` emits
        # `trade_date/daily_pnl` — not `date`/`equity`/`pnl`. A wrong name
        # here returns an EMPTY series rather than raising, so the chart
        # would simply be blank and nothing would say why.
        "equity_curve": _series(
            compute_equity_curve(df), "trade_date", "cumulative_pnl"
        ),
        "daily_pnl": _series(daily_pnl(df), "trade_date", "daily_pnl"),
        "streaks": {
            "current": sample_pair(
                need(streaks, "current_streak"), insufficient_for(df, 1)
            ),
            "max_win": sample_pair(
                need(streaks, "max_win_streak"), insufficient_for(df, 1)
            ),
            "max_loss": sample_pair(
                need(streaks, "max_loss_streak"), insufficient_for(df, 1)
            ),
        },
    }


def build_risk(df: pd.DataFrame) -> Dict[str, Any]:
    """Lens 2 — how much was at stake, and what did it cost?"""
    if df.empty:
        return {
            "max_drawdown": dict(_UNDEFINED_NO_SAMPLE),
            "drawdown_series": [],
            "r_multiples": [],
            "avg_win": dict(_UNDEFINED_NO_SAMPLE),
            "avg_loss": dict(_UNDEFINED_NO_SAMPLE),
        }

    basic = compute_basic_metrics(df)
    complete = pnl_is_complete(df)
    curve = compute_equity_curve(df)

    return {
        # A drawdown needs at least two points to exist. `compute_max_drawdown`
        # returns a finite 0.0 below that, which `pair` cannot distinguish
        # from a real flat period — hence the caller-side gate.
        "max_drawdown": sample_pair(
            compute_max_drawdown(curve),
            insufficient_for(df, MIN_DRAWDOWN_POINTS) or not complete,
        ),
        "drawdown_series": _series(drawdown_series(df), "trade_date", "drawdown"),
        "r_multiples": _histogram(r_multiple_distribution(df)),
        "avg_win": money_pair(
            need(basic, "avg_win"),
            complete=complete and int(need(basic, "wins")) > 0,
        ),
        "avg_loss": money_pair(
            need(basic, "avg_loss"),
            complete=complete and int(need(basic, "losses")) > 0,
        ),
    }


def _series(
    built: pd.DataFrame, date_column: str, value_column: str
) -> List[Dict[str, Any]]:
    """A dated series as wire rows, dropping points that cannot be plotted.

    A NaN in the middle of an equity curve is not a zero and must not be
    drawn as one; the point is omitted and the gap is visible.
    """
    # Both column names are REQUIRED arguments and are asserted present: a
    # mistyped name must fail loudly, not yield an empty chart that reads as
    # "no trades". Guessing a date column by position was how the first
    # draft of this plan would have silently emptied three charts.
    if built is None or built.empty:
        return []
    if date_column not in built.columns or value_column not in built.columns:
        raise KeyError(
            "series expects {!r} and {!r}, got {}".format(
                date_column, value_column, list(built.columns)
            )
        )
    rows: List[Dict[str, Any]] = []
    for _, row in built.iterrows():
        number, _state = finite_or_state(row[value_column])
        if number is None:
            continue
        rows.append({"date": str(row[date_column]), "value": number})
    return rows


def _histogram(built: pd.DataFrame) -> List[Dict[str, Any]]:
    """R-multiple buckets as `{label, count}`.

    VERIFIED: `r_multiple_distribution` emits `bin_left/bin_right/count`.
    The label is built from the two edges — taking `columns[0]` would print
    a bare bin edge like `-1.5` as though it were a category name.
    """
    if built is None or built.empty:
        return []
    return [
        {
            "label": "{:.1f} to {:.1f}R".format(
                float(row["bin_left"]), float(row["bin_right"])
            ),
            "count": int(row["count"]),
        }
        for _, row in built.iterrows()
    ]
