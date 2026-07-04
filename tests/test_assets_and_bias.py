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


# ---------------------------------------------------------------------------
# Item 3 — futures contract month-code stripping (mapper-layer normalization).
# Month codes: F G H J K M N Q U V X Z, with optional 2- or 4-digit years.
# ---------------------------------------------------------------------------


def test_strip_contract_month_examples():
    from src.tradelens.services.assets import strip_contract_month

    cases = {
        "MNQU": "MNQ",  # month code stripped
        "MNQZ": "MNQ",
        "ESZ": "ES",
        "NQH": "NQ",
        "ESHU": "ESH",  # spread qualifier kept — base ES has it by convention
        "NGG2026": "NG",  # the reported bug case
        "NGGU2026": "NG",
        "MNQU2026": "MNQ",
        "MNQH26": "MNQ",  # 2-digit year (TradingView short form)
        "NGX2026": "NG",
        "6EZ": "6E",
        "MCLF2026": "MCL",
    }
    for raw, expected in cases.items():
        assert strip_contract_month(raw) == expected, raw


def test_strip_never_removes_base_ticker_letters():
    from src.tradelens.services.assets import strip_contract_month

    # Known bases ending in a month-code letter must NOT be stripped.
    for base in ("MNQ", "NQ", "NG", "ES", "M2K", "HG", "ZN"):
        assert strip_contract_month(base) == base


def test_strip_leaves_forex_and_unknown_tickers_alone():
    from src.tradelens.services.assets import strip_contract_month

    assert strip_contract_month("EURUSD") == "EURUSD"
    assert strip_contract_month("gbp/usd") == "GBPUSD"  # normalization preserved
    assert strip_contract_month("AMZN") == "AMZN"  # ends in N (month code) — kept
    assert strip_contract_month("") == ""
    assert strip_contract_month(None) == ""
