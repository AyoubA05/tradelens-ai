"""
Strategy Profile parsing helpers (Session E, P7).
"""

from src.tradelens.services.strategy import (
    parse_list,
    parse_markets,
    parse_mistakes,
    parse_setups,
    parse_timeframes,
)


def test_parse_markets_splits_commas_and_and():
    assert parse_markets({"markets": "NQ, MNQ and NG"}) == ["NQ", "MNQ", "NG"]


def test_parse_markets_uppercases_and_dedups():
    assert parse_markets({"markets": "nq, NQ, es"}) == ["NQ", "ES"]


def test_parse_markets_empty():
    assert parse_markets({}) == []
    assert parse_markets(None) == []


def test_parse_list_preserves_multitoken_items():
    text = "Liquidity Sweep + FVG, BOS + OB Retest, IFVG entry"
    assert parse_list(text) == [
        "Liquidity Sweep + FVG",
        "BOS + OB Retest",
        "IFVG entry",
    ]


def test_parse_list_does_not_split_on_slash():
    assert parse_list("S/R Bounce, FVG") == ["S/R Bounce", "FVG"]


def test_parse_timeframes_entry_and_htf():
    tf = parse_timeframes({"timeframes": "1m entry, 15m HTF"})
    assert tf == {"entry": "1m", "htf": "15m"}


def test_parse_timeframes_normalizes_hours():
    tf = parse_timeframes({"timeframes": "5m entry, 4h HTF"})
    assert tf == {"entry": "5m", "htf": "4H"}


def test_parse_setups_and_mistakes():
    assert parse_setups({"setups_traded": "BOS + OB Retest, IFVG Entry"}) == [
        "BOS + OB Retest",
        "IFVG Entry",
    ]
    assert parse_mistakes({"common_mistakes": "FOMO Entry, Late Entry"}) == [
        "FOMO Entry",
        "Late Entry",
    ]
