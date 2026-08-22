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
    """The boundary rejects NaN and Infinity, so the service must not emit them."""
    import json

    from src.tradelens.api.serialization import to_jsonable

    owner, _ = seeded
    json.dumps(
        to_jsonable(overview.build_overview(user_id=owner, **PERIOD)), allow_nan=False
    )


def test_recent_trades_are_newest_first_and_capped(seeded):
    owner, _ = seeded
    rows = overview.build_overview(user_id=owner, **PERIOD)["recent_trades"]
    assert len(rows) <= 5
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
