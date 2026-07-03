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

Direction is display-only (prices are applied; direction is inferred from
entry/stop downstream). P&L is transcribed only from a visible on-chart label and
applied opt-in downstream; the trade RESULT (Win/Loss) stays the trader's to enter.
Risk/reward ratio, overall confidence, and the visible OCR labels are cross-check
context and are never written into the form.
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
    # Extraction-contract additions (screenshot_v3). Cross-check context, except
    # pnl which is opt-in autofill downstream; RR/confidence/labels never written.
    risk_reward_ratio: Optional[str] = None
    pnl: Optional[float] = None
    overall_confidence: Optional[str] = None
    visible_labels: list = field(default_factory=list)

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


_CONFIDENCE_LEVELS = {"high", "medium", "low"}


def _as_number(value) -> Optional[float]:
    """A signed number (P&L can be negative), or None. Bools/junk -> None.

    Tolerates a currency/thousands-formatted string ("$1,234.50") because the
    value is transcribed from an on-chart label, not a typed number field.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        s = value.strip().replace(",", "").replace("$", "")
        if not s:
            return None
        try:
            return float(s)
        except ValueError:
            return None
    return None


def _normalize_rr(value) -> Optional[str]:
    """Normalize a risk/reward value to a "<r>:1" string, or None (never guess).

    Accepts a bare number (2.01 -> "2.01:1"), a plain numeric string ("3" ->
    "3:1"), or an "a:b" string ("2.01:1" -> "2.01:1", "3:2" -> "1.5:1"). Anything
    unparseable, or a non-positive ratio, returns None.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        r = float(value)
    elif isinstance(value, str):
        s = value.strip().replace(",", "")
        if not s:
            return None
        if ":" in s:
            num, _, den = s.partition(":")
            try:
                a, b = float(num), float(den)
            except ValueError:
                return None
            if b == 0:
                return None
            r = a / b
        else:
            try:
                r = float(s)
            except ValueError:
                return None
    else:
        return None
    if r <= 0 or r != r or r in (float("inf"), float("-inf")):
        return None
    return f"{r:g}:1"


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

    # Extraction-contract additions — each fails safe to None/[] when absent.
    overlay.pnl = _as_number(section.get("pnl"))
    overlay.risk_reward_ratio = _normalize_rr(section.get("risk_reward_ratio"))

    oc = section.get("overall_confidence")
    if isinstance(oc, str) and oc.strip().lower() in _CONFIDENCE_LEVELS:
        overlay.overall_confidence = oc.strip().lower()

    labels = section.get("visible_labels")
    if isinstance(labels, list):
        overlay.visible_labels = [
            s.strip() for s in labels if isinstance(s, str) and s.strip()
        ]

    return overlay


# ---------------------------------------------------------------------------
# Per-field provenance — was a value read from a printed label, estimated from
# the drawn markup geometry, or not visible at all? Derived entirely from the
# existing visible_labels/source fields; no change to the vision JSON contract.
# ---------------------------------------------------------------------------

PROVENANCE_TEXT = {
    "label": "read from visible label",
    "markup": "estimated from markup",
    "none": "not visible",
}


def _price_variants(value: float) -> list:
    """Printable forms of a price to look for inside a transcribed label."""
    variants = {str(value), f"{value:.2f}"}
    if float(value).is_integer():
        variants.add(str(int(value)))
    # Single-character forms ("1", "5") would false-match timeframe labels
    # like "1m"; a real price label always prints more than one character.
    return [v for v in variants if len(v) >= 3]


def field_provenance(overlay: TradeOverlay, fieldname: str) -> str:
    """Provenance of an overlay price field: "label", "markup", or "none".

    "label" when the value literally appears in one of the exact label strings
    the model transcribed (visible_labels); "markup" when the value exists but
    was only estimated from the drawn geometry; "none" when it isn't visible.
    """
    value = getattr(overlay, fieldname, None)
    if value is None:
        return "none"
    try:
        variants = _price_variants(float(value))
    except (TypeError, ValueError):
        return "markup"
    for label in overlay.visible_labels:
        cleaned = str(label).replace(",", "")
        if any(v in cleaned for v in variants):
            return "label"
    return "markup"


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
