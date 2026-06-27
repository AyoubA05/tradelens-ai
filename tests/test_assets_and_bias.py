"""
Session E: asset-class auto-detection + legacy Bias display mapping.
"""

from src.tradelens.services.assets import OTHER, curated_assets, detect_asset_class
from src.tradelens.utils.format import humanize


def test_detect_asset_class_futures():
    assert detect_asset_class("NQ") == "Futures"
    assert detect_asset_class("MNQ") == "Futures"
    assert detect_asset_class("NG") == "Futures"


def test_detect_asset_class_forex():
    assert detect_asset_class("EURUSD") == "Forex"
    assert detect_asset_class("xauusd") == "Forex"  # case-insensitive
    assert detect_asset_class("GBP/USD") == "Forex"  # slash normalized
    assert detect_asset_class(" gbp / usd ") == "Forex"  # slash + spaces


def test_detect_asset_class_crypto():
    assert detect_asset_class("BTCUSD") == "Crypto"
    assert detect_asset_class("ETHUSD") == "Crypto"


def test_detect_asset_class_unknown_returns_none():
    assert detect_asset_class("WEIRDSYM") is None
    assert detect_asset_class("") is None
    assert detect_asset_class(None) is None


def test_curated_assets_contains_each_class_and_other_is_sentinel():
    curated = curated_assets()
    assert "NQ" in curated and "EURUSD" in curated and "BTCUSD" in curated
    assert OTHER not in curated  # OTHER is the custom sentinel, not a symbol


def test_legacy_neutral_bias_displays_as_consolidation():
    assert humanize("neutral") == "Consolidation"
    assert humanize("Neutral") == "Consolidation"
    assert humanize("consolidation") == "Consolidation"


def test_other_bias_values_unchanged():
    assert humanize("bullish") == "Bullish"
    assert humanize("bearish") == "Bearish"
