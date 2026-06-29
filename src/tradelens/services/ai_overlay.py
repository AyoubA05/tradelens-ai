"""
Trade-overlay parsing for screenshot_v3 (Session F, Phase 3).

Pure and Streamlit-free. The screenshot_v3 vision schema has two sections:

  * ``descriptive`` — chart context (bias, structure, SMC flags, key zones). This
    feeds the descriptive autofill via ai_autofill.map_analysis_to_form, which is
    contractually forbidden from proposing direction/prices. ``descriptive_section``
    is the bridge: it flattens the v3 section to the flat keys that mapper reads
    (and passes a flat v2-style dict straight through, for back-compat).

  * ``trade_overlay`` — the visible trade-box / chart-markup geometry the trader
    already drew (direction + prices), each with a confidence score. This is a
    SEPARATE path: ``parse_trade_overlay`` normalizes it, and the UI shows it as
    "approximate from visible markup — confirm before saving". It never flows
    through map_analysis_to_form, so Phase 1's no-prices guarantee is preserved.

Per Phase-3 decisions: direction is display-only (prices are applied; direction is
inferred from entry/stop downstream), and P&L / result are intentionally excluded.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

OVERLAY_PRICE_FIELDS = ("entry_price", "stop_price", "tp_price", "exit_price")
_DIRECTIONS = {"long", "short"}
_SOURCES = {"visible_trade_box", "visible_chart_markup", "none"}


@dataclass
class TradeOverlay:
    """Normalized visible trade-box geometry. Approximate; never auto-applied.

    ``direction`` is display/cross-check only (Phase-3 decision 5): the form infers
    direction from entry/stop, so only the prices are ever applied.
    """

    direction: Optional[str] = None
    entry_price: Optional[float] = None
    stop_price: Optional[float] = None
    tp_price: Optional[float] = None
    exit_price: Optional[float] = None
    confidence: dict = field(default_factory=dict)  # field name -> clamped [0,1]
    source: str = "none"

    def has_prices(self) -> bool:
        return any(getattr(self, f) is not None for f in OVERLAY_PRICE_FIELDS)


def _clamp01(value) -> float:
    """Coerce a confidence to a float in [0.0, 1.0]; non-numeric -> 0.0."""
    try:
        f = float(value)
    except (TypeError, ValueError):
        return 0.0
    return 0.0 if f < 0 else 1.0 if f > 1 else f


def _as_price(value) -> Optional[float]:
    """A usable price float, or None. Booleans are rejected (not real prices)."""
    if isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def parse_trade_overlay(analysis, min_confidence: float = 0.0) -> TradeOverlay:
    """Normalize the ``trade_overlay`` section into a TradeOverlay.

    Drops fields that are null, non-numeric, or below ``min_confidence``; clamps
    every confidence to [0,1]; validates the ``direction`` and ``source`` enums.
    Non-dict input (or a missing section) yields an empty overlay (source "none").
    """
    overlay = TradeOverlay()
    if not isinstance(analysis, dict):
        return overlay
    section = analysis.get("trade_overlay")
    if not isinstance(section, dict):
        return overlay

    src = section.get("source")
    overlay.source = src if src in _SOURCES else "none"

    conf_in = section.get("confidence")
    conf_in = conf_in if isinstance(conf_in, dict) else {}

    for fieldname in OVERLAY_PRICE_FIELDS:
        price = _as_price(section.get(fieldname))
        if price is None:
            continue
        c = _clamp01(conf_in.get(fieldname))
        if c < min_confidence:
            continue
        setattr(overlay, fieldname, price)
        overlay.confidence[fieldname] = c

    direction = section.get("direction")
    if direction in _DIRECTIONS:
        c = _clamp01(conf_in.get("direction"))
        if c >= min_confidence:
            overlay.direction = direction
            overlay.confidence["direction"] = c

    return overlay


def descriptive_section(analysis) -> dict:
    """Flatten the v3 ``descriptive`` section to the keys Phase 1's mapper reads.

    A flat v2-style dict (no ``descriptive`` key) passes straight through. Also
    normalizes two v3-only shape changes for the read-only observations panel:
    ``matched_strategy`` (bool) -> its reason string, and string mistake/missed
    fields -> single-item lists.
    """
    if not isinstance(analysis, dict):
        return {}
    section = analysis.get("descriptive")
    section = section if isinstance(section, dict) else analysis
    out = dict(section)

    ms = out.get("matched_strategy")
    if isinstance(ms, bool):
        out["matched_strategy"] = out.get("matched_strategy_reason") if ms else None

    for key in ("possible_mistakes", "missed_opportunities"):
        value = out.get(key)
        if isinstance(value, str):
            out[key] = [value] if value.strip() else []

    return out
