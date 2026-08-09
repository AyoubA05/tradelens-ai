from __future__ import annotations

from types import MappingProxyType
from typing import Mapping


STARTER_TEMPLATE: Mapping[str, str] = MappingProxyType(
    {
        "name": "ICT/SMC Day Trading",
        "trading_style": "ICT / SMC",
        "markets": "NQ, ES, EURUSD, GBP/USD",
        "timeframes": "15m entry, 1H/4H HTF",
        "entry_rules": (
            "Wait for HTF POI, confirm BOS or CHoCH on LTF, "
            "enter on FVG or OB retest"
        ),
        "stop_rules": "Place SL below/above the swing that caused the BOS",
        "take_profit_rules": "TP at next liquidity level or opposing HTF POI",
        "risk_rules": (
            "Max 1% per trade, max 2 trades per session, no revenge trading"
        ),
        "setups_traded": "Liquidity Sweep + FVG, BOS + OB Retest, CHoCH Entry",
        "setups_avoided": (
            "Counter-trend without BOS, news candle entries, off-session trades"
        ),
        "common_mistakes": ("FOMO entry, moving SL, off-session trades, overtrading"),
    }
)

# These groups mirror the Strategy page's six sections exactly. A section is
# written when any one of its stored fields has a non-blank value.
SECTION_FIELDS = (
    ("name",),
    ("entry_rules",),
    ("stop_rules", "take_profit_rules"),
    ("risk_rules",),
    ("setups_traded", "setups_avoided", "news_session_rules"),
    ("common_mistakes",),
)


def demo_strategy_profile() -> dict[str, str]:
    return dict(STARTER_TEMPLATE)


def profile_completion(profile: Mapping[str, object]) -> tuple[int, int]:
    written = sum(
        any(str(profile.get(field) or "").strip() for field in fields)
        for fields in SECTION_FIELDS
    )
    return written, len(SECTION_FIELDS)
