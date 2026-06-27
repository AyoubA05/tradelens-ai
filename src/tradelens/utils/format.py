"""
Display formatting helpers (Session A, Section 5 — UI polish).

Turns raw stored tokens into human-readable labels so the UI never shows
``None``, ``nan``, ``off_session``, ``limit`` or ``market`` to the user.
Streamlit-free and pure, so it is trivially unit-testable.
"""

from __future__ import annotations

EMPTY = "—"

# Explicit labels for tokens whose Title-Case would read wrong (acronyms, etc.).
_LABELS = {
    "off_session": "Off Session",
    "asia": "Asia",
    "london": "London",
    "london_open": "London Open",
    "london_close": "London Close",
    "ny_am": "New York AM",
    "ny_lunch": "New York Lunch",
    "ny_pm": "New York PM",
    "limit": "Limit",
    "market": "Market",
    "stop_limit": "Stop Limit",
    # Bias wording (Session E): legacy "neutral" displays as "Consolidation".
    "neutral": "Consolidation",
    "consolidation": "Consolidation",
    "bullish": "Bullish",
    "bearish": "Bearish",
}


def humanize(value) -> str:
    """Readable label for a raw value.

    None / NaN / empty → "—". Known tokens map to friendly labels; anything else
    falls back to Title Case (``stop_limit`` → "Stop Limit", ``london`` → "London").
    """
    if value is None:
        return EMPTY
    text = str(value).strip()
    if not text or text.lower() in ("nan", "none"):
        return EMPTY
    key = text.lower()
    if key in _LABELS:
        return _LABELS[key]
    return text.replace("_", " ").title() if ("_" in text or text.islower()) else text
