"""
AI Autofill mapping (Session F, Phase 1).

Translates the screenshot_v2 vision output (see services/vision.py) into editable
New Trade form values, so a trader can review/accept AI suggestions before saving.

Design rules:
  * Pure and Streamlit-free — reusable from any UI or test.
  * AI proposes DESCRIPTIVE fields only: asset, timeframe, HTF/LTF bias, and the
    SMC confluence flags. It never proposes direction, prices, P&L, or result —
    this is post-trade reflection, not a signal.
  * trade_quality / mistakes / notes stay read-only "observations" — shown to the
    trader but never written into form fields automatically.
  * Returns only the fields the AI actually gave a usable value for, so accepting
    a suggestion never overwrites a form default with None.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable, Optional

from src.tradelens.services.assets import normalize_symbol, strip_contract_month

# Vision bias vocabulary -> New Trade BIAS_OPTIONS (Bullish/Bearish/Consolidation).
_BIAS_MAP = {
    "bullish": "Bullish",
    "bearish": "Bearish",
    "neutral": "Consolidation",
    "consolidation": "Consolidation",
    "ranging": "Consolidation",
    "range": "Consolidation",
    "sideways": "Consolidation",
}

# Vision timeframe strings -> New Trade TIMEFRAMES (1m/5m/15m/1H/4H/D).
_TIMEFRAME_MAP = {
    "1m": "1m",
    "5m": "5m",
    "15m": "15m",
    "1h": "1H",
    "60m": "1H",
    "60min": "1H",
    "4h": "4H",
    "240m": "4H",
    "d": "D",
    "1d": "D",
    "daily": "D",
}

# Vision boolean SMC flags -> New Trade CONFLUENCES labels, in display order.
_CONFLUENCE_FLAGS = (
    ("liquidity_sweep", "Liquidity Sweep"),
    ("fvg_used", "FVG"),
    ("ifvg_used", "IFVG"),
    ("order_block_used", "OB Retest"),
    ("bos", "BOS"),
    ("choch", "MSS/CHOCH"),
)

# Zone-description words that mean price already entered/broke the FVG (Item 6).
# Deliberately tight — "broke structure" alone must not remap an FVG.
_MITIGATION_MARKERS = (
    "mitigat",
    "invert",
    "traded through",
    "traded into",
    "broken through",
    "broke through",
    "filled",
)

# Read-only fields surfaced to the trader but never auto-applied to form values.
# instrument_name is the long chart title (e.g. "Micro E-mini Nasdaq-100 …") — the
# form only takes the short ticker, so the long name is context, never a prefill.
_OBSERVATION_KEYS = (
    "trade_quality",
    "possible_mistakes",
    "missed_opportunities",
    "notes_to_user",
    "structure",
    "matched_strategy",
    "matched_strategy_reason",
    "key_zones",
    "bias_confidence",
    "instrument_name",
)
_LIST_OBSERVATIONS = {"possible_mistakes", "missed_opportunities", "key_zones"}


@dataclass
class AutofillResult:
    """Result of mapping a vision analysis to New Trade form values.

    prefill:      field -> value, present ONLY when the AI gave a usable value.
    observations: read-only AI notes (empty when there is no analysis).
    ai_fields:    prefill keys that are AI-sourced, in a stable order (for badges).
    asset_in_list: True/False when ``known_assets`` is supplied and an asset was
                   detected; None otherwise.
    """

    prefill: dict = field(default_factory=dict)
    observations: dict = field(default_factory=dict)
    ai_fields: list = field(default_factory=list)
    asset_in_list: Optional[bool] = None


def normalize_bias(value: Optional[str]) -> Optional[str]:
    """Map a vision bias string to a New Trade bias option, or None if unmappable."""
    if not value:
        return None
    return _BIAS_MAP.get(str(value).strip().lower())


def normalize_timeframe(value: Optional[str]) -> Optional[str]:
    """Map a vision timeframe string to the app's timeframe set, or None.

    Only timeframes representable in the New Trade set (1m/5m/15m/1H/4H/D) map;
    anything else (e.g. '30m', 'weekly') returns None rather than guessing.
    """
    if not value:
        return None
    return _TIMEFRAME_MAP.get(str(value).strip().lower().replace(" ", ""))


# Conservative true-like encodings — a flag must be one of these to count.
# Guards against a model returning the *string* "false" (non-empty → truthy)
# and silently adding a confluence the trader never had.
_TRUE_STRINGS = {"true", "1", "yes"}


def _is_truthy_flag(value) -> bool:
    """True only for genuine true-like booleans (True, 1, or 'true'/'1'/'yes').

    Rejects False/0/None, the string "false", and any other arbitrary string —
    so a malformed flag fails closed (no spurious confluence) rather than open.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value == 1
    if isinstance(value, str):
        return value.strip().lower() in _TRUE_STRINGS
    return False


def _fvg_traded_through(analysis: dict) -> bool:
    """Evidence in the response that an FVG zone was entered/broken (Item 6).

    True when a key zone is typed "ifvg", or an "fvg" zone's description says
    price mitigated/inverted/traded through it — i.e. the FVG is really an IFVG.
    """
    zones = analysis.get("key_zones")
    if not isinstance(zones, list):
        return False
    for zone in zones:
        if not isinstance(zone, dict):
            continue
        ztype = str(zone.get("type") or "").strip().lower()
        if ztype == "ifvg":
            return True
        desc = str(zone.get("description") or "").lower()
        if ztype == "fvg" and any(m in desc for m in _MITIGATION_MARKERS):
            return True
    return False


def confluences_from_analysis(analysis: Optional[dict]) -> list:
    """Confluence labels for the true-like SMC flags in a vision analysis.

    Item 6: a FVG that price has since traded into or through is an IFVG, not
    an FVG — when the response's own zones show mitigation, FVG remaps to IFVG.
    """
    if not isinstance(analysis, dict):
        return []
    labels = [
        label for key, label in _CONFLUENCE_FLAGS if _is_truthy_flag(analysis.get(key))
    ]
    if "FVG" in labels and _fvg_traded_through(analysis):
        idx = labels.index("FVG")
        labels.remove("FVG")
        if "IFVG" not in labels:
            labels.insert(idx, "IFVG")
    return labels


def _extract_observations(analysis: dict) -> dict:
    out: dict = {}
    for key in _OBSERVATION_KEYS:
        val = analysis.get(key)
        if val is None and key in _LIST_OBSERVATIONS:
            val = []
        out[key] = val
    return out


def map_analysis_to_form(
    analysis: Optional[dict],
    known_assets: Optional[Iterable[str]] = None,
) -> AutofillResult:
    """Map a screenshot_v2 vision analysis to editable New Trade form values.

    Args:
        analysis: The vision result dict (see services/vision.py). Non-dict input
                  yields an empty result so callers never have to guard.
        known_assets: Optional iterable of the form's asset options. When given,
                      ``asset_in_list`` reports whether the detected asset matches
                      one (so the UI can choose the dropdown vs the custom field).

    Returns:
        AutofillResult with prefill / observations / ai_fields / asset_in_list.
    """
    result = AutofillResult()
    if not isinstance(analysis, dict):
        return result

    result.observations = _extract_observations(analysis)

    # asset (normalized so 'gbp/usd' matches the curated 'GBPUSD'; futures
    # contract month/year suffixes are stripped here in the mapper — Item 3 —
    # so 'MNQU2026' reaches the form as 'MNQ').
    # Non-string values (a malformed model response) fail safe: omit the asset.
    detected_asset = analysis.get("detected_asset")
    if isinstance(detected_asset, str) and detected_asset.strip():
        asset = strip_contract_month(detected_asset)
        if asset:
            result.prefill["asset"] = asset
            result.ai_fields.append("asset")
            if known_assets is not None:
                known = {normalize_symbol(a) for a in known_assets}
                result.asset_in_list = asset in known

    # timeframe
    timeframe = normalize_timeframe(analysis.get("detected_timeframe"))
    if timeframe:
        result.prefill["timeframe"] = timeframe
        result.ai_fields.append("timeframe")

    # HTF bias <- vision "htf_bias"; LTF bias <- vision "bias"
    htf = normalize_bias(analysis.get("htf_bias"))
    if htf:
        result.prefill["htf_bias"] = htf
        result.ai_fields.append("htf_bias")

    ltf = normalize_bias(analysis.get("bias"))
    if ltf:
        result.prefill["ltf_bias"] = ltf
        result.ai_fields.append("ltf_bias")

    # confluence flags
    confluences = confluences_from_analysis(analysis)
    if confluences:
        result.prefill["confluences"] = confluences
        result.ai_fields.append("confluences")

    return result
