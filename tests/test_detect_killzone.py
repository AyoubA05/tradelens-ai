"""
detect_killzone (Session E, P0): NY AM starts at 09:30 in the user's timezone.

These lock the bug fix so 9:30/10:15 ET never regress back to Off Session / a
10:30 NY-AM start.
"""

import datetime as dt

import pytest

from src.tradelens.services.sessions import detect_killzone


@pytest.mark.parametrize(
    "hh,mm,expected",
    [
        (9, 30, "ny_am"),  # market open — the regression guard
        (10, 15, "ny_am"),  # Ayoub ICT window
        (11, 59, "ny_am"),
        (9, 29, "london_open"),
        (2, 0, "london_open"),
        (12, 0, "ny_lunch"),
        (12, 59, "ny_lunch"),
        (13, 0, "ny_pm"),
        (15, 59, "ny_pm"),
        (16, 30, "off_session"),
        (20, 0, "asia"),
        (1, 0, "asia"),
    ],
)
def test_detect_killzone_windows(hh, mm, expected):
    assert detect_killzone(dt.time(hh, mm)) == expected


def test_detect_killzone_930_is_ny_am():
    assert detect_killzone(dt.time(9, 30)) == "ny_am"


def test_detect_killzone_1015_is_ny_am():
    assert detect_killzone(dt.time(10, 15)) == "ny_am"


def test_detect_killzone_accepts_string():
    assert detect_killzone("09:30") == "ny_am"
    assert detect_killzone("10:15") == "ny_am"


def test_detect_killzone_tz_aware_converted():
    # 14:30 UTC == 09:30 America/New_York (EDT, summer) → NY AM, not server tz.
    aware = dt.datetime(2026, 6, 24, 14, 30, tzinfo=dt.timezone.utc)
    assert detect_killzone(aware, user_timezone="America/New_York") == "ny_am"


def test_detect_killzone_none_is_off_session():
    assert detect_killzone(None) == "off_session"
