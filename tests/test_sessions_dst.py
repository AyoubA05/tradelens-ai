"""
DST-edge tests for killzone assignment (Phase 5, week6-d5, flow-pass §i).

Killzones are evaluated in US Eastern time, so the SAME UTC instant maps to a
different killzone depending on whether DST is in effect. These tests prove the
conversion is DST-aware (not a naive fixed offset).

2026 US DST: spring forward Sun Mar 8; fall back Sun Nov 1.
"""

import datetime as dt
from zoneinfo import ZoneInfo

from src.tradelens.services.sessions import assign_killzone

_UTC = ZoneInfo("UTC")


def test_ny_am_during_edt():
    # Mar 9 (EDT, UTC-4): 11:00 UTC == 07:00 ET -> NY AM killzone.
    assert assign_killzone(dt.datetime(2026, 3, 9, 11, 0, tzinfo=_UTC)) == "ny_am"


def test_same_utc_is_off_session_during_est():
    # Nov 9 (EST, UTC-5): 11:00 UTC == 06:00 ET -> before NY AM -> off-session.
    assert assign_killzone(dt.datetime(2026, 11, 9, 11, 0, tzinfo=_UTC)) is None


def test_dst_changes_killzone_for_same_utc():
    march = assign_killzone(dt.datetime(2026, 3, 9, 11, 0, tzinfo=_UTC))
    november = assign_killzone(dt.datetime(2026, 11, 9, 11, 0, tzinfo=_UTC))
    assert march != november  # DST awareness, not a fixed offset


def test_ny_pm_shifts_with_dst():
    # 13:30 ET == NY PM start in both seasons, but at different UTC times.
    assert assign_killzone(dt.datetime(2026, 3, 9, 17, 30, tzinfo=_UTC)) == "ny_pm"
    assert assign_killzone(dt.datetime(2026, 11, 9, 18, 30, tzinfo=_UTC)) == "ny_pm"


def test_naive_datetime_assumed_utc():
    # Naive input is treated as UTC by default; Mar 9 11:00 -> NY AM.
    assert assign_killzone(dt.datetime(2026, 3, 9, 11, 0)) == "ny_am"
