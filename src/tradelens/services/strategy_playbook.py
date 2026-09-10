"""The Strategy Profile's fixed shape: its six sections and its starter template.

Pure data and one pure function. It lives in services/ because the FastAPI
layer and the Streamlit page both need it, and services/ must never import
from ui/ (which is retired in Phase 10). `ui/components/strategy_profile.py`
re-exports these names so Streamlit reads the same objects, not copies.
"""

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

SECTION_LABELS = (
    "Identity",
    "Entry Rules",
    "Exit Rules",
    "Risk Rules",
    "Setups",
    "Self-Awareness",
)

SECTION_IDS = ("identity", "entry", "exit", "risk", "setups", "self_awareness")

# How many times the same correction must repeat before it is offered as a
# Strategy Profile rule. One value, read by Streamlit and the API alike.
REPEAT_THRESHOLD = 5


def section_status(profile: Mapping[str, object]) -> list:
    """`[(section_id, label, written), ...]` in page order.

    The one place "is this section written" is decided. `profile_completion`
    counts these, so the API's per-section flags and its total cannot drift.
    """
    return [
        (
            section_id,
            label,
            any(str(profile.get(field) or "").strip() for field in fields),
        )
        for section_id, label, fields in zip(
            SECTION_IDS, SECTION_LABELS, SECTION_FIELDS
        )
    ]


def profile_completion(profile: Mapping[str, object]) -> tuple[int, int]:
    written = sum(1 for _id, _label, done in section_status(profile) if done)
    return written, len(SECTION_FIELDS)
