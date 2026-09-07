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


def _trades_frame(rows):
    return pd.DataFrame(rows)


def _winning_row(**over):
    row = {
        "id": 1,
        "trade_date": "2026-09-01",
        "asset": "NQ",
        "direction": "Long",
        "result": "Win",
        "pnl": 250.0,
        "rr_realized": 2.0,
        "rr_planned": 2.0,
        "session": "New York",
        "killzone": "ny_am",
        "setup_type": "FVG",
        "confirmation_model": "BOS",
        "strategy_used": "ICT",
        "timeframe": "5m",
        "day_of_week": "Tuesday",
        "entry_time": "09:35",
        "followed_rules": 1,
        "mistake_tags": "[]",
    }
    row.update(over)
    return row


def test_expectancy_is_read_from_the_metrics_dict_not_recomputed():
    """`compute_expectancy` takes the metrics DICT, not the frame.

    Passing the frame would raise or, worse, silently produce a different
    number — this pins the call shape as well as the value.
    """
    from src.tradelens.services.metrics import (
        compute_basic_metrics,
        compute_expectancy,
    )

    df = _trades_frame([_winning_row(), _winning_row(id=2, result="Loss", pnl=-100.0)])
    built = an.build_performance(df)

    assert built["expectancy"]["value"] == pytest.approx(
        compute_expectancy(compute_basic_metrics(df))
    )


def test_a_journal_with_no_pnl_reports_no_total_rather_than_zero():
    """The process-only journal: prices and notes, P&L never filled in."""
    df = _trades_frame(
        [_winning_row(pnl=None), _winning_row(id=2, pnl=None, result="Loss")]
    )
    built = an.build_performance(df)

    assert built["total_pnl"] == {
        "value": None,
        "state": "undefined_incomplete_sample",
    }


def test_profit_factor_with_no_losses_is_infinite_not_a_big_number():
    df = _trades_frame([_winning_row(), _winning_row(id=2)])
    assert (
        an.build_performance(df)["profit_factor"]["state"]
        == "undefined_positive_infinity"
    )


def test_max_drawdown_under_two_points_is_undefined_not_zero():
    """A single trade has no drawdown to measure. 0.0 would claim it does."""
    df = _trades_frame([_winning_row()])
    assert an.build_risk(df)["max_drawdown"]["state"] == "undefined_no_sample"


def test_an_empty_sample_reports_every_figure_as_undefined():
    """Not one plausible zero anywhere on the page."""
    built = an.build_performance(pd.DataFrame())
    for field in ("total_pnl", "win_rate", "expectancy", "profit_factor"):
        assert built[field]["value"] is None, field
        assert built[field]["state"] is not None, field


def test_a_measured_zero_pnl_is_not_reported_as_undefined():
    """The other direction, and it matters just as much.

    A trader who genuinely broke even measured 0.00. Reporting that as "no
    data" would erase a real result — over-gating is as wrong as under-gating.
    """
    df = _trades_frame(
        [
            _winning_row(pnl=100.0),
            _winning_row(id=2, result="Loss", pnl=-100.0),
        ]
    )
    built = an.build_performance(df)
    assert built["total_pnl"] == {"value": 0.0, "state": None}
    # The sample-size gate must not fire on a sample that HAS the rows: a
    # win rate over two trades is measured, not withheld.
    assert built["win_rate"] == {"value": 0.5, "state": None}


def test_a_nan_point_is_omitted_from_a_series_not_drawn_as_zero():
    """A gap in an equity curve is a gap. Plotting it at 0 invents a drawdown."""
    built = an._series(
        pd.DataFrame(
            {
                "trade_date": ["2026-09-01", "2026-09-02", "2026-09-03"],
                "cumulative_pnl": [250.0, float("nan"), 400.0],
            }
        ),
        "trade_date",
        "cumulative_pnl",
    )
    assert built == [
        {"date": "2026-09-01", "value": 250.0},
        {"date": "2026-09-03", "value": 400.0},
    ]


def test_a_mistyped_series_column_raises_rather_than_emptying_the_chart():
    """The silent failure this whole shape exists to prevent.

    A wrong column name must not return `[]` — a blank chart reads as "no
    trades" and nothing says otherwise.
    """
    with pytest.raises(KeyError):
        an._series(
            pd.DataFrame({"trade_date": ["2026-09-01"], "cumulative_pnl": [1.0]}),
            "date",
            "equity",
        )


def test_a_partly_filled_pnl_column_is_not_a_total():
    """`.all()`, not `.any()` — and only a MIXED sample can tell them apart.

    One trade with P&L and one without does not sum to the trader's result:
    it is the total of the rows they happened to fill in. An all-blank
    column cannot catch a `.any()` mistake, because `.any()` is also False
    there — this is the sample that does.
    """
    df = _trades_frame([_winning_row(pnl=250.0), _winning_row(id=2, pnl=None)])
    assert an.pnl_is_complete(df) is False
    assert (
        an.build_performance(df)["total_pnl"]["state"] == "undefined_incomplete_sample"
    )
