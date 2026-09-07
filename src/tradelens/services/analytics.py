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
