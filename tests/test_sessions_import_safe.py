"""
Regression: sessions.py must import and run even when the IANA tz database is
unavailable (the Streamlit Cloud crash where module-level ZoneInfo raised).
"""

import datetime as dt
from zoneinfo import ZoneInfoNotFoundError

import src.tradelens.services.sessions as sessions

_VALID = {"asia", "london_open", "ny_am", "ny_lunch", "ny_pm", "off_session"}


def test_no_module_level_zoneinfo_constant():
    # The crash was `ET = ZoneInfo(...)` at import time — it must be gone.
    assert not hasattr(sessions, "ET")


def test_zone_falls_back_when_tzdb_missing(monkeypatch):
    def boom(_name):
        raise ZoneInfoNotFoundError("No time zone found")

    monkeypatch.setattr(sessions, "ZoneInfo", boom)
    # Never raises — returns the fixed fallback offset.
    assert sessions._zone("America/New_York") is sessions._ET_FALLBACK
    # Wall-clock detection needs no tz db at all.
    assert sessions.detect_killzone(dt.time(9, 30)) == "ny_am"
    # tz-aware conversion degrades gracefully instead of crashing.
    aware = dt.datetime(2026, 6, 26, 14, 30, tzinfo=dt.timezone.utc)
    assert sessions.detect_killzone(aware, user_timezone="America/New_York") in _VALID
    assert sessions.assign_killzone(dt.datetime(2026, 6, 26, 14, 30)) in _VALID | {None}


def test_killzone_still_correct_with_real_tzdb():
    # Sanity: with tzdata present (locally), behavior is unchanged.
    assert sessions.detect_killzone(dt.time(9, 30)) == "ny_am"
    assert sessions.detect_killzone(dt.time(10, 15)) == "ny_am"
