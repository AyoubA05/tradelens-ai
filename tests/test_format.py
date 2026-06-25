"""Tests for the display-formatting helper (Session A, Section 5)."""

import numpy as np

from src.tradelens.utils.format import humanize


def test_none_and_nan_become_dash():
    assert humanize(None) == "—"
    assert humanize(float("nan")) == "—"
    assert humanize(np.nan) == "—"
    assert humanize("") == "—"
    assert humanize("none") == "—"


def test_known_tokens_mapped():
    assert humanize("off_session") == "Off Session"
    assert humanize("limit") == "Limit"
    assert humanize("market") == "Market"
    assert humanize("ny_am") == "New York AM"
    assert humanize("stop_limit") == "Stop Limit"


def test_fallback_title_cases_snake_and_lower():
    assert humanize("london") == "London"
    assert humanize("some_new_token") == "Some New Token"


def test_already_pretty_passthrough():
    assert humanize("NQ") == "NQ"
    assert humanize("Win") == "Win"
