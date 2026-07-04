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


# ---------------------------------------------------------------------------
# Item 7 — parse_price: exact decimal precision, no rounding or truncation.
# ---------------------------------------------------------------------------


def test_parse_price_preserves_any_precision():
    from src.tradelens.utils.format import parse_price

    assert parse_price("3.496") == 3.496
    assert parse_price("3.3765") == 3.3765
    assert parse_price("19850.25") == 19850.25
    assert parse_price("2.7555") == 2.7555
    assert parse_price("1.08432") == 1.08432  # 5-dp forex


def test_parse_price_tolerates_commas_and_whitespace():
    from src.tradelens.utils.format import parse_price

    assert parse_price(" 19,850.25 ") == 19850.25
    assert parse_price("30,433.25") == 30433.25


def test_parse_price_empty_and_junk_return_none():
    from src.tradelens.utils.format import parse_price

    for bad in ("", "   ", None, "abc", "1.2.3"):
        assert parse_price(bad) is None
