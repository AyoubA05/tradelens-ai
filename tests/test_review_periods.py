import datetime as dt

import pandas as pd
import pytest

from src.tradelens.db.models import Trade
from src.tradelens.db.session import SessionLocal
from src.tradelens.services import app_settings, review_periods
from src.tradelens.ui.components import review_dates, review_reader


def _trade(owner, day):
    db = SessionLocal()
    try:
        db.add(
            Trade(
                user_id=owner,
                asset="NQ",
                direction="Long",
                result="Win",
                trade_date=day,
                pnl=10.0,
            )
        )
        db.commit()
    finally:
        db.close()


def test_streamlit_keeps_the_same_functions():
    assert review_dates.review_day_options is review_periods.review_day_options
    assert review_dates.review_week_options is review_periods.review_week_options
    assert review_reader.period_stats is review_periods.period_stats


def test_week_options_are_mondays_newest_first():
    frame = pd.DataFrame({"trade_date": ["2026-09-02", "2026-09-10", "bad", None]})
    assert review_periods.review_week_options(frame) == (
        dt.date(2026, 9, 7),
        dt.date(2026, 8, 31),
    )


def test_owner_options_are_owner_scoped_and_never_future(two_users):
    a, b = two_users
    _trade(a, "2026-09-08")
    _trade(a, "2026-09-20")  # after "today"
    _trade(b, "2026-09-01")
    today = dt.date(2026, 9, 14)
    assert review_periods.completed_day_options(a, today=today) == (
        dt.date(2026, 9, 8),
    )
    assert review_periods.completed_week_options(a, today=today) == (
        dt.date(2026, 9, 7),
    )


def test_period_stats_of_nothing_is_zeroed():
    stats = review_periods.period_stats(pd.DataFrame())
    assert stats["trades"] == 0
    assert stats["financial_status"] == "no_sample"


def test_period_stats_distinguish_missing_pnl_from_a_measured_zero():
    incomplete = review_periods.period_stats(
        pd.DataFrame({"result": ["Win"], "pnl": [None]})
    )
    measured_zero = review_periods.period_stats(
        pd.DataFrame({"result": ["Breakeven"], "pnl": [0.0]})
    )

    assert incomplete["total_pnl"] == measured_zero["total_pnl"] == 0.0
    assert incomplete["financial_status"] == "incomplete"
    assert measured_zero["financial_status"] == "measured"


def _utc(*parts):
    return dt.datetime(*parts, tzinfo=dt.timezone.utc)


# Decision C6. Each case is a DST-transition Sunday and the UTC instants either
# side of the following Monday's LOCAL midnight — which moved with the offset.
# A rule using the pre-transition offset (or UTC) lands on the wrong side.
_DST_CASES = [
    # New York springs forward 2026-03-08; Monday 00:00 EDT is 04:00Z.
    (
        "America/New_York",
        dt.date(2026, 3, 8),
        _utc(2026, 3, 9, 3, 59),
        _utc(2026, 3, 9, 4, 0),
    ),
    # New York falls back 2026-11-01; Monday 00:00 EST is 05:00Z.
    (
        "America/New_York",
        dt.date(2026, 11, 1),
        _utc(2026, 11, 2, 4, 59),
        _utc(2026, 11, 2, 5, 0),
    ),
    # London springs forward 2026-03-29; Monday 00:00 BST is Sunday 23:00Z.
    (
        "Europe/London",
        dt.date(2026, 3, 29),
        _utc(2026, 3, 29, 22, 59),
        _utc(2026, 3, 29, 23, 0),
    ),
    # London falls back 2026-10-25; Monday 00:00 GMT is 00:00Z.
    (
        "Europe/London",
        dt.date(2026, 10, 25),
        _utc(2026, 10, 25, 23, 59),
        _utc(2026, 10, 26, 0, 0),
    ),
]


@pytest.mark.parametrize("zone, sunday, before, after", _DST_CASES)
def test_options_follow_the_owner_zone_across_dst(
    two_users, zone, sunday, before, after
):
    owner, other = two_users
    monday = sunday + dt.timedelta(days=1)
    previous_monday = sunday - dt.timedelta(days=6)
    app_settings.set_timezone(owner, zone)
    _trade(owner, sunday.isoformat())
    _trade(owner, monday.isoformat())
    _trade(other, monday.isoformat())

    today = app_settings.today_for_owner(owner, now_utc=before)
    assert today == sunday
    assert review_periods.completed_day_options(owner, today=today) == (sunday,)
    assert review_periods.completed_week_options(owner, today=today) == (
        previous_monday,
    )

    today = app_settings.today_for_owner(owner, now_utc=after)
    assert today == monday
    assert review_periods.completed_day_options(owner, today=today) == (
        monday,
        sunday,
    )
    assert review_periods.completed_week_options(owner, today=today) == (
        monday,
        previous_monday,
    )


@pytest.mark.parametrize("zone, sunday", [(c[0], c[1]) for c in _DST_CASES])
def test_the_transition_sunday_itself_is_today(two_users, zone, sunday):
    owner, _ = two_users
    app_settings.set_timezone(owner, zone)
    _trade(owner, sunday.isoformat())
    # 15:00Z on the transition Sunday is after the switch in both zones.
    today = app_settings.today_for_owner(
        owner, now_utc=dt.datetime.combine(sunday, dt.time(15, 0), dt.timezone.utc)
    )
    assert today == sunday
    assert review_periods.completed_day_options(owner, today=today) == (sunday,)
