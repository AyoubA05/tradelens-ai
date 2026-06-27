"""
Curated instrument lists + asset-class detection (Session E).

Pure and Streamlit-free so the New Trade form can offer a searchable asset
dropdown and auto-lock the asset class. Unknown symbols (custom entries) return
None so the UI can let the user pick the class manually.
"""

from __future__ import annotations

from typing import Optional

FUTURES = [
    "NQ",
    "MNQ",
    "ES",
    "MES",
    "YM",
    "MYM",
    "RTY",
    "M2K",
    "CL",
    "MCL",
    "GC",
    "MGC",
    "SI",
    "HG",
    "NG",
    "ZB",
    "ZN",
    "6E",
    "6B",
    "6J",
    "6A",
    "6C",
    "6S",
]
FOREX = [
    "EURUSD",
    "GBPUSD",
    "USDJPY",
    "USDCHF",
    "USDCAD",
    "AUDUSD",
    "NZDUSD",
    "EURJPY",
    "GBPJPY",
    "EURGBP",
    "EURAUD",
    "EURCAD",
    "AUDJPY",
    "CADJPY",
    "XAUUSD",
    "XAGUSD",
]
CRYPTO = [
    "BTCUSD",
    "ETHUSD",
    "SOLUSD",
    "XRPUSD",
    "BNBUSD",
    "ADAUSD",
    "DOGEUSD",
    "AVAXUSD",
    "LINKUSD",
    "LTCUSD",
]

OTHER = "Other / Custom"

_CLASS_BY_SYMBOL = {
    **{s: "Futures" for s in FUTURES},
    **{s: "Forex" for s in FOREX},
    **{s: "Crypto" for s in CRYPTO},
}


def normalize_symbol(symbol: Optional[str]) -> str:
    """Uppercase, strip spaces, and drop slashes so 'gbp/usd' matches 'GBPUSD'."""
    if not symbol:
        return ""
    return symbol.strip().upper().replace("/", "").replace(" ", "")


def detect_asset_class(symbol: Optional[str]) -> Optional[str]:
    """Return 'Futures' | 'Forex' | 'Crypto' for a known symbol, else None.

    Normalization makes display variants ('GBP/USD', ' eurusd ') match the
    backend symbols ('GBPUSD', 'EURUSD').
    """
    if not symbol:
        return None
    return _CLASS_BY_SYMBOL.get(normalize_symbol(symbol))


def curated_assets() -> list:
    """All curated symbols in display order (Futures → Forex → Crypto)."""
    return [*FUTURES, *FOREX, *CRYPTO]
