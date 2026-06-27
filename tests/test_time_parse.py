"""
Typed Entry Time parsing (Session E1, P0 #4).
"""

import datetime as dt

import pytest

from src.tradelens.services.sessions import detect_killzone, parse_time_input


@pytest.mark.parametrize(
    "text,expected",
    [
        ("09:30", dt.time(9, 30)),
        ("9:30 AM", dt.time(9, 30)),
        ("9:30AM", dt.time(9, 30)),
        ("2:05 PM", dt.time(14, 5)),
        ("14:05", dt.time(14, 5)),
        ("0930", dt.time(9, 30)),
        ("12:00 PM", dt.time(12, 0)),
        ("12:00 AM", dt.time(0, 0)),
    ],
)
def test_parse_valid_times(text, expected):
    assert parse_time_input(text) == expected


@pytest.mark.parametrize("text", ["", "  ", "not a time", "25:99", "abc", None])
def test_parse_invalid_returns_none(text):
    assert parse_time_input(text) is None


def test_parse_passthrough_time_object():
    t = dt.time(10, 15)
    assert parse_time_input(t) == t


def test_typed_930_am_maps_to_ny_am():
    # The end-to-end behavior the New Trade form relies on.
    assert detect_killzone(parse_time_input("9:30 AM")) == "ny_am"
    assert detect_killzone(parse_time_input("10:15")) == "ny_am"
