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


@pytest.mark.parametrize(
    "rows",
    [
        [_winning_row(pnl=None), _winning_row(id=2, pnl=None, result="Loss")],
        [_winning_row(pnl=250.0), _winning_row(id=2, pnl=None, result="Loss")],
    ],
    ids=["all-missing", "partly-missing"],
)
def test_incomplete_pnl_cannot_become_a_ratio_or_money_series(rows):
    """Metric helpers fill missing P&L with zero; the projection must not.

    The scalar total already refused an incomplete sample, but the same sample
    still produced a 0.00x/∞ profit factor and flat zero points in the equity,
    daily-P&L and drawdown charts. Those pictures contradict the scalar and are
    more likely to be trusted because they look measured.
    """
    df = _trades_frame(rows)

    performance = an.build_performance(df)
    risk = an.build_risk(df)

    assert performance["profit_factor"] == {
        "value": None,
        "state": "undefined_incomplete_sample",
    }
    assert performance["equity_curve"] == []
    assert performance["daily_pnl"] == []
    assert risk["max_drawdown"] == {
        "value": None,
        "state": "undefined_incomplete_sample",
    }
    assert risk["drawdown_series"] == []


def test_an_all_breakeven_sample_has_no_profit_factor_not_a_measured_zero():
    """With neither profits nor losses there is no ratio to divide."""
    df = _trades_frame(
        [
            _winning_row(result="Breakeven", pnl=0.0),
            _winning_row(id=2, result="Breakeven", pnl=0.0),
        ]
    )

    assert an.build_performance(df)["profit_factor"] == {
        "value": None,
        "state": "undefined_no_sample",
    }


def test_average_win_survives_missing_pnl_on_an_unrelated_breakeven():
    """An incomplete row outside the winner set does not erase a measured mean."""
    df = _trades_frame(
        [
            _winning_row(result="Win", pnl=125.0),
            _winning_row(id=2, result="Breakeven", pnl=None),
        ]
    )

    assert an.build_risk(df)["avg_win"] == {"value": 125.0, "state": None}


def test_a_breakdown_reports_whether_it_can_be_compared():
    """One category is not a ranking.

    The Streamlit page already refuses to call a single setup "best"; the API
    has to carry that judgement rather than leaving the browser to guess,
    or the two surfaces will disagree about the same sample.
    """
    df = _trades_frame([_winning_row(), _winning_row(id=2)])  # one setup only
    built = an.build_setups(df)

    assert built["by_setup"]["comparable"] is False
    assert len(built["by_setup"]["rows"]) == 1


def test_two_categories_are_comparable():
    df = _trades_frame(
        [_winning_row(), _winning_row(id=2, setup_type="OB", result="Loss", pnl=-50.0)]
    )
    assert an.build_setups(df)["by_setup"]["comparable"] is True


def test_a_breakdown_row_with_no_pnl_carries_an_undefined_total():
    df = _trades_frame([_winning_row(pnl=None), _winning_row(id=2, pnl=None)])
    rows = an.build_setups(df)["by_setup"]["rows"]

    assert rows[0]["total_pnl"]["state"] == "undefined_incomplete_sample"


def test_a_breakdown_row_with_pnl_carries_the_measured_total():
    """The other direction: gating must not swallow a figure that exists."""
    df = _trades_frame([_winning_row(pnl=250.0), _winning_row(id=2, pnl=250.0)])
    rows = an.build_setups(df)["by_setup"]["rows"]

    assert rows[0]["total_pnl"] == {"value": 500.0, "state": None}
    assert rows[0]["trades"] == 2


def test_rule_adherence_over_rows_that_never_recorded_it_is_undefined():
    """A blank `followed_rules` is not a broken rule.

    Counting unrecorded rows as violations would tell a trader their
    discipline was 0% when they simply had not filled the field in.
    """
    df = _trades_frame(
        [_winning_row(followed_rules=None), _winning_row(id=2, followed_rules=None)]
    )
    assert an.build_discipline(df)["rule_adherence"]["state"] == "undefined_no_sample"


def test_rule_adherence_that_was_recorded_is_reported():
    """The gate is the RECORDED count, not the row count.

    Gating on `len(df)` would look identical on the sample above while
    silently withholding a discipline figure the trader did record.
    """
    df = _trades_frame(
        [_winning_row(followed_rules=1), _winning_row(id=2, followed_rules=0)]
    )
    built = an.build_discipline(df)
    assert built["rule_adherence"] == {"value": 0.5, "state": None}
    assert built["recorded_trades"] == 2


def test_consistency_below_five_trades_is_undefined_not_zero():
    """Phase 2 shipped "0 out of 100" to a four-trade trader. Not again."""
    df = _trades_frame([_winning_row(id=i) for i in range(4)])
    assert an.build_discipline(df)["consistency"]["state"] == "undefined_no_sample"


def test_a_fully_recorded_clean_process_keeps_its_measured_zero_edge_leak():
    """No qualifying rule breaks is exactly zero leak, not missing data."""
    df = _trades_frame(
        [
            _winning_row(followed_rules=1, mistake_tags="[]"),
            _winning_row(
                id=2,
                result="Loss",
                pnl=-100.0,
                followed_rules=1,
                mistake_tags="[]",
            ),
        ]
    )

    assert an.build_discipline(df)["edge_leak"] == {"value": 0.0, "state": None}


def test_unrecorded_process_rows_do_not_yield_a_partial_edge_leak_total():
    """A known breach beside an unknown row is not the whole sample's leak."""
    df = _trades_frame(
        [
            _winning_row(followed_rules=0, pnl=-100.0),
            _winning_row(id=2, followed_rules=None, mistake_tags="", pnl=-50.0),
        ]
    )

    assert an.build_discipline(df)["edge_leak"] == {
        "value": None,
        "state": "undefined_incomplete_sample",
    }


def test_a_breakdown_leader_is_not_named_below_the_shared_pattern_threshold():
    """Two categories can be compared as rows without earning a narrative."""
    df = _trades_frame(
        [
            _winning_row(setup_type="FVG", pnl=500.0),
            _winning_row(id=2, setup_type="OB", pnl=-50.0, result="Loss"),
        ]
    )

    built = an.build_setups(df)["by_setup"]
    assert built["comparable"] is True
    assert built["leader"] is None


def test_a_breakdown_leader_comes_from_the_shared_metric_policy():
    rows = [
        _winning_row(id=index, setup_type="FVG", pnl=100.0) for index in range(1, 5)
    ]
    rows.append(_winning_row(id=5, setup_type="OB", pnl=-50.0, result="Loss"))

    built = an.build_setups(_trades_frame(rows))["by_setup"]
    assert built["leader"] == {"key": "FVG", "trades": 4}


def test_mistake_frequency_over_an_empty_sample_is_an_empty_list():
    assert an.build_setups(pd.DataFrame())["mistakes"] == []


def test_comparison_money_is_undefined_when_either_period_has_missing_pnl():
    current = _trades_frame(
        [_winning_row(pnl=100.0), _winning_row(id=2, pnl=None, result="Loss")]
    )
    prior = _trades_frame(
        [_winning_row(id=3, pnl=50.0), _winning_row(id=4, pnl=-25.0, result="Loss")]
    )

    built = an.build_comparison(current, prior, ("2026-08-01", "2026-08-31"))

    assert built["net_pnl"] == {
        "value": None,
        "state": "undefined_incomplete_sample",
    }
    assert built["profit_factor"] == {
        "value": None,
        "state": "undefined_incomplete_sample",
    }
    # Outcome labels are independently complete and remain measurable.
    assert built["win_rate"]["value"] is not None


@pytest.mark.parametrize("result,pnl", [("Win", 100.0), ("Breakeven", 0.0)])
def test_comparison_does_not_fabricate_a_profit_factor_delta_without_a_ratio(
    result, pnl
):
    current = _trades_frame(
        [
            _winning_row(result=result, pnl=pnl),
            _winning_row(id=2, result=result, pnl=pnl),
        ]
    )
    prior = _trades_frame(
        [
            _winning_row(id=3, result=result, pnl=pnl),
            _winning_row(id=4, result=result, pnl=pnl),
        ]
    )

    built = an.build_comparison(current, prior, ("2026-08-01", "2026-08-31"))

    assert built["profit_factor"] == {
        "value": None,
        "state": "undefined_no_sample",
    }


def test_comparison_keeps_a_real_zero_profit_factor_delta_for_all_losses():
    current = _trades_frame(
        [
            _winning_row(result="Loss", pnl=-100.0),
            _winning_row(id=2, result="Loss", pnl=-50.0),
        ]
    )
    prior = _trades_frame(
        [
            _winning_row(id=3, result="Loss", pnl=-25.0),
            _winning_row(id=4, result="Loss", pnl=-75.0),
        ]
    )

    assert an.build_comparison(current, prior, ("2026-08-01", "2026-08-31"))[
        "profit_factor"
    ] == {"value": 0.0, "state": None}


def test_the_timing_lens_breaks_the_sample_down_by_when_it_traded():
    """Not vacuous: this asserts the real keys arrive, not that a list exists.

    A wrong key column would yield `{"rows": [], "comparable": False}` —
    the same shape as an honest empty breakdown, and indistinguishable
    without pinning the value.
    """
    df = _trades_frame(
        [
            _winning_row(day_of_week="Tuesday", session="New York"),
            _winning_row(id=2, day_of_week="Friday", session="London", pnl=-50.0),
        ]
    )
    built = an.build_timing(df)

    assert {row["key"] for row in built["by_day_of_week"]["rows"]} == {
        "Tuesday",
        "Friday",
    }
    assert {row["key"] for row in built["by_session"]["rows"]} == {
        "New York",
        "London",
    }
    assert built["by_day_of_week"]["comparable"] is True


def test_the_timing_lens_does_not_offer_an_hour_breakdown_it_cannot_fill():
    """`entry_time` is hash-only, so no stored trade carries a clock time.

    `metrics.by_hour_of_day` therefore returns zero rows for every real
    sample. Shipping the panel anyway would show a trader an empty "by hour"
    chart, which reads as "you have no hourly pattern" rather than "this app
    never stored the hour" — a claim about their record that we invented.
    """
    df = pd.DataFrame(
        [
            {
                "id": 1,
                "trade_date": "2026-09-01",
                "asset": "NQ",
                "result": "Win",
                "pnl": 100.0,
                "session": "New York",
                "killzone": "ny_am",
                "setup_type": "FVG",
                "day_of_week": "Tuesday",
                "entry_time": "09:35",
            }
        ]
    )
    assert "by_hour" not in an.build_timing(df)
    assert "by_hour" not in an.build_timing(pd.DataFrame())
