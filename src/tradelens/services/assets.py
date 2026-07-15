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


# CME/NYMEX/COMEX futures delivery-month codes (Jan..Dec).
_MONTH_CODES = set("FGHJKMNQUVXZ")
_ALL_KNOWN = set(FUTURES) | set(FOREX) | set(CRYPTO)


def strip_contract_month(symbol: Optional[str]) -> str:
    """Normalize a futures contract symbol to its base ticker (Item 3).

    MNQU→MNQ, ESZ→ES, NQH→NQ, NGG2026→NG, NGGU2026→NG, MNQH26→MNQ, ESHU→ESH.

    Safety rules:
      * A known symbol (MNQ, NG, EURUSD) is never stripped — base tickers that
        happen to end in a month-code letter (MNQ, NG, HG) keep it.
      * Without a year suffix, a trailing letter is treated as a month code only
        when the remainder resolves to a known base — directly (MNQU→MNQ) or
        through one spread qualifier whose own base is known (ESHU→ESH, ES is
        known). Stock-like tickers (AMZN) therefore pass through untouched.
      * A 2- or 4-digit year marks a definite dated contract, so month letters
        are peeled until a known base emerges (NGGU2026→NG).
    """
    s = normalize_symbol(symbol)
    if not s or s in _ALL_KNOWN:
        return s

    # Optional 2- or 4-digit year suffix (NGG2026, MNQH26).
    no_digits = s.rstrip("0123456789")
    year_len = len(s) - len(no_digits)
    had_year = year_len in (2, 4) and len(no_digits) >= 2
    base = no_digits if had_year else s
    if base in _ALL_KNOWN:
        return base

    if had_year:
        candidate = base
        while (
            candidate not in _ALL_KNOWN
            and len(candidate) > 2
            and candidate[-1] in _MONTH_CODES
        ):
            candidate = candidate[:-1]
        if candidate in _ALL_KNOWN:
            return candidate
        if len(base) > 2 and base[-1] in _MONTH_CODES:
            return base[:-1]  # best effort: unknown base, single month strip
        return base

    if len(base) > 2 and base[-1] in _MONTH_CODES:
        remainder = base[:-1]
        if remainder in _ALL_KNOWN:
            return remainder
        # One spread qualifier is kept when its own base is known (ESHU→ESH).
        if (
            len(remainder) > 2
            and remainder[-1] in _MONTH_CODES
            and remainder[:-1] in _ALL_KNOWN
        ):
            return remainder
    return base


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


def tradable_assets() -> list:
    """Symbols offered in the New Trade asset dropdown: futures and forex only
    (Item 5 — the journal's supported scope). Crypto stays recognizable to the
    classifier for legacy rows but is no longer offered for new trades."""
    return [*FUTURES, *FOREX]
