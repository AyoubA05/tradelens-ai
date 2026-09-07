"""Phase 6 analytics projection: undefined never becomes zero."""

from __future__ import annotations

import pandas as pd
import pytest

from src.tradelens.services import analytics as an


def test_a_real_zero_stays_a_measured_zero():
    """A trader who broke exactly even measured 0.00. That is an answer."""
    assert an.pair(0.0) == {"value": 0.0, "state": None}


def test_nan_becomes_an_undefined_state_not_a_zero():
    assert an.pair(float("nan"))["value"] is None
    assert an.pair(float("nan"))["state"] == "undefined_nan"


def test_infinite_profit_factor_is_named_not_flattened():
    """A profit factor with no losing trades is infinite, not huge and not 0."""
    assert an.pair(float("inf")) == {
        "value": None,
        "state": "undefined_positive_infinity",
    }


def test_none_is_no_sample_rather_than_a_silent_null():
    assert an.pair(None) == {"value": None, "state": "undefined_no_sample"}


def test_money_over_rows_that_do_not_record_pnl_is_incomplete_not_zero():
    """THE money rule. A journal with prices but no P&L has not made $0."""
    assert an.money_pair(0.0, complete=False) == {
        "value": None,
        "state": "undefined_incomplete_sample",
    }
    assert an.money_pair(250.0, complete=True) == {"value": 250.0, "state": None}


def test_a_metric_that_flattens_low_sample_to_zero_is_gated_by_the_caller():
    """`finite_or_state` cannot see this: 0.0 is finite.

    max_drawdown below two points, consistency below five trades and a win
    rate over zero trades all return an ordinary 0.0, so only the caller's
    knowledge of the sample size can tell "measured zero" from "no answer".
    """
    assert an.sample_pair(0.0, insufficient=True)["state"] == "undefined_no_sample"
    assert an.sample_pair(0.0, insufficient=False) == {"value": 0.0, "state": None}


def test_reading_a_missing_metric_key_raises_rather_than_defaulting():
    """A renamed metric must break loudly, not render a plausible $0.00.

    Phase 2's plan wrapped every read in `.get(col, 0.0)` and would have
    shipped five undefined figures as zero.
    """
    with pytest.raises(KeyError):
        an.need({"total_pnl": 1.0}, "net_pnl")


def test_the_frame_of_no_trades_is_empty_not_a_row_of_zeroes():
    built = an.frame([])
    assert isinstance(built, pd.DataFrame)
    assert built.empty
