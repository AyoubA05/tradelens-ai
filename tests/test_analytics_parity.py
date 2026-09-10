"""The API's figures and `services/metrics`' figures are the same figures.

A trader with the Streamlit page and the new page open must not see two
different win rates. There is no way for them to tell which one is lying, so
the only acceptable difference is none.

This compares the PROJECTION against the metric functions directly, field by
field, over one shared frame. It is deliberately not a snapshot test: a
snapshot pins whatever the code currently does, including a mistake, whereas
this pins the projection to its source of truth. `services/metrics.py` is
parity-pinned — when one of these fails, the projection is what moves.
"""

from __future__ import annotations

import pandas as pd
import pytest

from src.tradelens.services import analytics as an
from src.tradelens.services import metrics as m


def _mixed_frame():
    """Wins, losses, a breakeven, two setups, two sessions, two assets.

    Deliberately varied: a single-category frame would make every breakdown
    one row long, and a projection that dropped or reordered rows would pass
    unnoticed.
    """
    rows = []
    for index, (result, pnl, setup, session, asset) in enumerate(
        [
            ("Win", 250.0, "FVG", "New York", "NQ"),
            ("Loss", -120.0, "FVG", "London", "ES"),
            ("Win", 480.0, "OB", "New York", "NQ"),
            ("Breakeven", 0.0, "OB", "London", "NQ"),
            ("Loss", -75.0, "FVG", "New York", "ES"),
            ("Win", 310.0, "OB", "New York", "NQ"),
        ]
    ):
        rows.append(
            {
                "id": index + 1,
                "trade_date": "2026-09-0{}".format(index + 1),
                "asset": asset,
                "direction": "Long",
                "result": result,
                "pnl": pnl,
                "rr_realized": round(pnl / 100.0, 2),
                "rr_planned": 2.0,
                "session": session,
                "killzone": "ny_am",
                "setup_type": setup,
                "confirmation_model": "BOS",
                "strategy_used": "ICT",
                "timeframe": "5m",
                "day_of_week": "Tuesday",
                "followed_rules": 1,
                "mistake_tags": "[]",
                "risk_amount": 100.0,
                "position_size": 1.0,
            }
        )
    return pd.DataFrame(rows)


def test_headline_performance_figures_match_the_metric_functions():
    df = _mixed_frame()
    basic = m.compute_basic_metrics(df)
    built = an.build_performance(df)

    assert built["total_pnl"]["value"] == pytest.approx(basic["total_pnl"])
    assert built["win_rate"]["value"] == pytest.approx(basic["win_rate"])
    assert built["expectancy"]["value"] == pytest.approx(m.compute_expectancy(basic))
    assert built["profit_factor"]["value"] == pytest.approx(
        m.compute_profit_factor_raw(df)
    )
    assert built["total_trades"] == len(df)


def test_the_equity_curve_matches_point_for_point():
    """Not just the length: a projection reading the wrong column returns an
    EMPTY list, and a projection reading the right column but the wrong row
    order draws a different account."""
    df = _mixed_frame()
    source = m.compute_equity_curve(df)
    points = an.build_performance(df)["equity_curve"]

    assert len(points) == len(source)
    assert [p["value"] for p in points] == [
        pytest.approx(v) for v in source["cumulative_pnl"]
    ]


def test_the_daily_pnl_series_matches_point_for_point():
    df = _mixed_frame()
    source = m.daily_pnl(df)
    points = an.build_performance(df)["daily_pnl"]

    assert len(points) == len(source)
    assert [p["value"] for p in points] == [
        pytest.approx(v) for v in source["daily_pnl"]
    ]


def test_risk_figures_match_the_metric_functions():
    df = _mixed_frame()
    built = an.build_risk(df)

    assert built["max_drawdown"]["value"] == pytest.approx(
        m.compute_max_drawdown(m.compute_equity_curve(df))
    )
    assert len(built["drawdown_series"]) == len(m.drawdown_series(df))
    assert len(built["r_multiples"]) == len(m.r_multiple_distribution(df))


def test_average_win_and_loss_match_the_metric_functions():
    df = _mixed_frame()
    basic = m.compute_basic_metrics(df)
    built = an.build_risk(df)

    assert built["avg_win"]["value"] == pytest.approx(basic["avg_win"])
    assert built["avg_loss"]["value"] == pytest.approx(basic["avg_loss"])


@pytest.mark.parametrize(
    "wire_key,metric_name,column",
    [
        ("by_day_of_week", "by_day_of_week", "day_of_week"),
        ("by_session", "by_session", "session"),
        ("by_killzone", "killzone_performance", "killzone"),
    ],
)
def test_every_timing_breakdown_matches_its_metric_function_row_for_row(
    wire_key, metric_name, column
):
    """Keys AND per-row totals.

    A projection that dropped a category, reordered rows, or summed a column
    itself would pass a count-only check.
    """
    df = _mixed_frame()
    source = getattr(m, metric_name)(df)
    rows = an.build_timing(df)[wire_key]["rows"]

    assert len(rows) == len(source)
    assert [r["key"] for r in rows] == [str(v) for v in source[column]]
    for wire_row, (_, source_row) in zip(rows, source.iterrows()):
        assert wire_row["trades"] == int(source_row["trades"])
        assert wire_row["total_pnl"]["value"] == pytest.approx(source_row["total_pnl"])


@pytest.mark.parametrize(
    "wire_key,metric_name,column",
    [
        ("by_setup", "setup_performance", "setup_type"),
        ("by_asset", "by_asset", "asset"),
        ("by_strategy", "by_strategy", "strategy_used"),
        ("by_timeframe", "by_timeframe", "timeframe"),
        ("by_confirmation", "confirmation_model_performance", "confirmation_model"),
    ],
)
def test_every_setups_breakdown_matches_its_metric_function_row_for_row(
    wire_key, metric_name, column
):
    df = _mixed_frame()
    source = getattr(m, metric_name)(df)
    rows = an.build_setups(df)[wire_key]["rows"]

    assert len(rows) == len(source)
    assert [r["key"] for r in rows] == [str(v) for v in source[column]]
    for wire_row, (_, source_row) in zip(rows, source.iterrows()):
        assert wire_row["trades"] == int(source_row["trades"])
        assert wire_row["total_pnl"]["value"] == pytest.approx(source_row["total_pnl"])
        assert wire_row["win_rate"]["value"] == pytest.approx(source_row["win_rate"])


def test_discipline_figures_match_the_metric_functions():
    df = _mixed_frame()
    built = an.build_discipline(df)

    assert built["consistency"]["value"] == pytest.approx(m.consistency_score(df))
    assert built["rule_adherence"]["value"] == pytest.approx(
        m.rule_adherence_rate(df).rate
    )
    assert built["recorded_trades"] == m.rule_adherence_rate(df).recorded
    assert built["edge_leak"]["value"] == pytest.approx(m.total_edge_leak(df))


def test_the_streak_figures_match_the_metric_function():
    df = _mixed_frame()
    source = m.compute_streaks(df)
    built = an.build_performance(df)["streaks"]

    assert built["current"]["value"] == pytest.approx(source["current_streak"])
    assert built["max_win"]["value"] == pytest.approx(source["max_win_streak"])
    assert built["max_loss"]["value"] == pytest.approx(source["max_loss_streak"])


def test_no_projected_figure_is_computed_rather_than_read():
    """A structural guard, not a value check.

    `services/analytics` must contain no arithmetic on money. Every number is
    read from a metric function; a formula here would be a second
    implementation of one that already exists, and the two would diverge the
    first time either changed.

    This is a blunt instrument — it would fire on a harmless `sum()` over row
    counts, and anyone determined can route around it. It is here because the
    alternative is trusting that nobody reimplements a formula, and the whole
    premise of this phase is that the two surfaces agree to the cent. Treat a
    failure as a prompt to justify the arithmetic, not a rule to evade.
    """
    import inspect

    source = inspect.getsource(an)
    for forbidden in ("sum(", ".mean()", ".sum()", "/ len(", "* 100"):
        assert forbidden not in source, "analytics computes: {}".format(forbidden)
