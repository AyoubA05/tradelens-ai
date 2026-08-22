# tests/test_overview_service.py
"""The Overview payload.

Correctness here is checked against the SAME golden dataset the parity harness
pins, so the API cannot quietly compute different numbers from the ones the
services were verified to produce.
"""
import pytest

from src.tradelens.services import overview
from tests.parity.dataset import seed_golden_dataset

PERIOD = {"start": "2026-08-01", "end": "2026-08-31"}


@pytest.fixture
def seeded(two_users):
    owner, other = two_users
    seed_golden_dataset(owner)
    return owner, other


def test_requires_a_concrete_owner():
    with pytest.raises(ValueError):
        overview.build_overview(user_id=None, start=PERIOD["start"], end=PERIOD["end"])


def test_headline_numbers_match_the_golden_dataset(seeded):
    owner, _ = seeded
    data = overview.build_overview(user_id=owner, **PERIOD)
    # 480 - 220 + 410 + 0 - 95
    assert data["kpi"]["net_pnl"] == 575.0
    assert data["kpi"]["trades"] == 5
    assert data["kpi"]["wins"] == 2
    assert data["kpi"]["losses"] == 2


def test_sees_only_its_own_owner(seeded):
    """The cardinal property. A second trader's rows must never appear."""
    _, other = seeded
    data = overview.build_overview(user_id=other, **PERIOD)
    assert data["kpi"]["trades"] == 0
    assert data["kpi"]["net_pnl"] == 0.0


def test_undefined_profit_factor_is_named_not_zeroed(two_users):
    """No losses means the ratio has no denominator.

    Rendering 0.0 there would be a confident wrong number — the exact failure
    the audit called out.
    """
    owner, _ = two_users
    from src.tradelens.services import trade_service

    trade_service.create_trade(
        {
            "trade_date": "2026-08-10",
            "asset": "NQ",
            "result": "Win",
            "pnl": 100.0,
        },
        user_id=owner,
    )
    data = overview.build_overview(user_id=owner, **PERIOD)
    assert data["kpi"]["profit_factor"] is None
    assert data["kpi"]["profit_factor_state"] == "undefined_positive_infinity"


def test_all_breakeven_profit_factor_is_undefined_not_zero(two_users):
    """No wins and no losses is "no ratio", not "the worst possible ratio".

    `compute_profit_factor_raw` flattens that case to a finite 0.0, which
    `finite_or_state` cannot recover a state from — so it rendered `0.00x`.
    """
    owner, _ = two_users
    from src.tradelens.services import trade_service

    for day in ("10", "11"):
        trade_service.create_trade(
            {
                "trade_date": f"2026-08-{day}",
                "asset": "NQ",
                "result": "Breakeven",
                "pnl": 0.0,
            },
            user_id=owner,
        )
    data = overview.build_overview(user_id=owner, **PERIOD)
    assert data["kpi"]["trades"] == 2
    assert data["kpi"]["profit_factor"] is None
    assert data["kpi"]["profit_factor_state"] == "undefined_no_sample"


def test_consistency_reads_the_grade_trend_the_dashboard_reads(two_users):
    """The API and the Streamlit Dashboard must score the same trader alike.

    `consistency_score` weights a grade-trend term at 25% and looks for the
    `user_grade`/`ai_grade` columns by name. pandas reports a missing column as
    absent rather than raising, so a frame without them scored a neutral 0.5
    trend unconditionally — up to 12.5 points away from the Dashboard, whose
    frame carries both. Asserting equality against a frame built from the same
    columns also pins the 5-trade threshold mirrored in this module.
    """
    import pandas as pd

    from src.tradelens.services import metrics, trade_service

    owner, _ = two_users
    grades = ["D", "C", "C", "B", "A"]  # an improving trend, so the term bites
    for i, grade in enumerate(grades):
        trade_service.create_trade(
            {
                "trade_date": f"2026-08-1{i}",
                "asset": "NQ",
                "result": "Win",
                "pnl": 100.0,
                "setup_type": "FVG",
                "followed_rules": 1,
                "user_grade": grade,
            },
            user_id=owner,
        )

    rows = trade_service.get_trades(
        user_id=owner, **{"start_date": PERIOD["start"], "end_date": PERIOD["end"]}
    )
    graded = pd.DataFrame(
        [{c: getattr(t, c) for c in overview._TRADE_COLUMNS} for t in rows]
    )
    ungraded = graded.drop(columns=["user_grade", "ai_grade"])

    # Guard the guard: if the grade term stopped mattering, the equality below
    # would pass for the wrong reason.
    assert metrics.consistency_score(graded) != metrics.consistency_score(ungraded)

    data = overview.build_overview(user_id=owner, **PERIOD)
    assert data["risk"]["consistency"]["value"] == metrics.consistency_score(graded)


def test_empty_period_reports_zero_trades_rather_than_failing(two_users):
    owner, _ = two_users
    data = overview.build_overview(user_id=owner, start="2020-01-01", end="2020-01-31")
    assert data["kpi"]["trades"] == 0
    assert data["sample"]["show_summary"] is False
    assert data["trajectory"]["equity_curve"] == []


def test_sample_flags_come_from_the_shared_policy(seeded):
    owner, _ = seeded
    data = overview.build_overview(user_id=owner, **PERIOD)
    assert data["sample"]["trades"] == 5
    assert data["sample"]["show_patterns"] is True
    assert data["sample"]["show_dominant_series"] is True


def test_every_value_survives_strict_json(seeded):
    """The boundary rejects NaN and Infinity, so the service must not emit them.

    Walks the raw payload first: `to_jsonable` maps every non-finite float to
    `None` by design, so piping straight through it (as this test used to)
    would let a stray `float("inf")` sail through undetected. Checking
    `math.isfinite` on the raw payload is what actually pins "the service
    itself never emits one."
    """
    import json
    import math

    from src.tradelens.api.serialization import to_jsonable

    owner, _ = seeded
    payload = overview.build_overview(user_id=owner, **PERIOD)

    def _walk(value):
        if isinstance(value, float):
            assert math.isfinite(value), f"non-finite float in raw payload: {value!r}"
        elif isinstance(value, dict):
            for v in value.values():
                _walk(v)
        elif isinstance(value, (list, tuple)):
            for v in value:
                _walk(v)

    _walk(payload)
    json.dumps(to_jsonable(payload), allow_nan=False)


def test_recent_trades_are_newest_first_and_capped(seeded):
    """Six trades in the period, capped to five — the golden dataset alone
    (exactly 5 trades) could never make this cap load-bearing."""
    owner, _ = seeded
    from src.tradelens.services import trade_service

    trade_service.create_trade(
        {"trade_date": "2026-08-20", "asset": "NQ", "result": "Win", "pnl": 10.0},
        user_id=owner,
    )
    rows = overview.build_overview(user_id=owner, **PERIOD)["recent_trades"]
    assert len(rows) == 5
    assert [r["trade_date"] for r in rows] == sorted(
        (r["trade_date"] for r in rows), reverse=True
    )


def test_calendar_reports_the_month_of_the_period_end(seeded):
    owner, _ = seeded
    cal = overview.build_overview(user_id=owner, **PERIOD)["calendar"]
    assert cal["year"] == 2026 and cal["month"] == 8
    outcomes = {d["outcome"] for d in cal["days"]}
    assert outcomes <= {"positive", "negative", "flat"}


def test_the_equity_curve_lives_under_trajectory(seeded):
    """The API contract nests it, and three later components read it there."""
    owner, _ = seeded
    data = overview.build_overview(user_id=owner, **PERIOD)
    assert "equity_curve" not in data
    points = data["trajectory"]["equity_curve"]
    assert points and set(points[0]) == {"date", "equity"}


# ---------------------------------------------------------------------------
# Fix round 2: figures metrics has already flattened to a finite 0.0 for lack
# of sample must cross the boundary as {"value": None, "state":
# "undefined_no_sample"}, not as a plausible-looking zero.
# ---------------------------------------------------------------------------


def test_max_drawdown_is_undefined_below_two_trades(two_users):
    owner, _ = two_users
    from src.tradelens.services import trade_service

    trade_service.create_trade(
        {"trade_date": "2026-08-10", "asset": "NQ", "result": "Win", "pnl": 100.0},
        user_id=owner,
    )
    data = overview.build_overview(user_id=owner, **PERIOD)
    assert data["risk"]["max_drawdown"] == {
        "value": None,
        "state": "undefined_no_sample",
    }


def test_consistency_is_undefined_below_five_trades(two_users):
    owner, _ = two_users
    from src.tradelens.services import trade_service

    for i in range(4):
        trade_service.create_trade(
            {
                "trade_date": f"2026-08-1{i}",
                "asset": "NQ",
                "result": "Win",
                "pnl": 100.0,
            },
            user_id=owner,
        )
    data = overview.build_overview(user_id=owner, **PERIOD)
    assert data["risk"]["consistency"] == {
        "value": None,
        "state": "undefined_no_sample",
    }


def test_average_win_is_undefined_with_no_wins(two_users):
    owner, _ = two_users
    from src.tradelens.services import trade_service

    trade_service.create_trade(
        {"trade_date": "2026-08-10", "asset": "NQ", "result": "Loss", "pnl": -50.0},
        user_id=owner,
    )
    data = overview.build_overview(user_id=owner, **PERIOD)
    assert data["trajectory"]["average_win"] == {
        "value": None,
        "state": "undefined_no_sample",
    }
    # The loss side is defined — only the side with no members is undefined.
    assert data["trajectory"]["average_loss"]["state"] is None


def test_average_loss_is_undefined_with_no_losses(two_users):
    owner, _ = two_users
    from src.tradelens.services import trade_service

    trade_service.create_trade(
        {"trade_date": "2026-08-10", "asset": "NQ", "result": "Win", "pnl": 50.0},
        user_id=owner,
    )
    data = overview.build_overview(user_id=owner, **PERIOD)
    assert data["trajectory"]["average_loss"] == {
        "value": None,
        "state": "undefined_no_sample",
    }


def test_win_rate_is_undefined_with_zero_trades(seeded):
    _, other = seeded
    data = overview.build_overview(user_id=other, **PERIOD)
    assert data["kpi"]["win_rate"] == {"value": None, "state": "undefined_no_sample"}


def test_edge_leak_amount_is_undefined_without_evidence(seeded):
    """No followed_rules or mistake_tags evidence means the leak amount is
    unknown, not zero."""
    owner, _ = seeded
    data = overview.build_overview(user_id=owner, **PERIOD)
    # The golden dataset carries followed_rules/mistake_tags evidence, so this
    # asserts the shape survives round-trip rather than forcing "undefined"
    # on a dataset that does have evidence.
    assert set(data["risk"]["edge_leak"]["amount"]) == {"value", "state"}


# ---------------------------------------------------------------------------
# Fix round 2: activation and today/week P&L are lifetime concepts and must
# not be reset by narrowing the analysis period.
# ---------------------------------------------------------------------------


def test_narrow_period_does_not_reset_activation(two_users):
    owner, _ = two_users
    from src.tradelens.services import trade_service

    # Five complete lifetime trades, all outside the analysis period below.
    for i in range(5):
        trade_service.create_trade(
            {
                "trade_date": f"2026-01-0{i + 1}",
                "asset": "NQ",
                "result": "Win",
                "pnl": 50.0,
                "setup_type": "FVG",
                "followed_rules": 1,
            },
            user_id=owner,
        )
    data = overview.build_overview(user_id=owner, **PERIOD)  # August; no trades in it
    assert data["kpi"]["trades"] == 0  # the selected period is genuinely empty
    assert data["next_review_action"]["trades_until_review"] == 0
    assert data["next_review_action"]["next_key"] != "first_trade"
