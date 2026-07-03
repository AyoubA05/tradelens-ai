"""
Post-trade screenshot analysis service.

Calls claude-fable-5 vision to review a chart image AFTER a trade has closed.
This is educational journaling only — not live trading advice.
"""

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Union

from src.tradelens.services.ai_client import (
    AIUnavailable,
    Usage,
    load_prompt,
    parse_ai_json,
    vision,
)
from src.tradelens.services.demo import is_demo, load_demo_fixture

_SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}

_EXPECTED_KEYS = {
    "bias",
    "bias_confidence",
    "detected_timeframe",
    "detected_asset",
    "structure",
    "bos",
    "choch",
    "key_zones",
    "matched_strategy",
    "matched_strategy_reason",
    "possible_mistakes",
    "missed_opportunities",
    "trade_quality",
    "notes_to_user",
    # SMC/ICT proposals (screenshot_v2) — editable pre-fills, never auto-applied
    "htf_bias",
    "liquidity_sweep",
    "fvg_used",
    "order_block_used",
}


class ScreenshotAnalysisError(Exception):
    """Raised when screenshot analysis cannot proceed due to input problems."""


# ---------------------------------------------------------------------------
# Screenshot quality pre-check (local, zero API spend)
# ---------------------------------------------------------------------------

# Below these the price-scale / symbol-bar text is usually unreadable to vision.
_MIN_WIDTH = 480
_MIN_HEIGHT = 320
# A chart screenshot is roughly landscape; a far more extreme ratio usually
# means a cropped strip (price axis or time axis cut off).
_MAX_ASPECT = 5.0


@dataclass
class ScreenshotQuality:
    """Result of the local pre-check run before a paid vision call.

    ``usable=False`` only when the file fundamentally cannot be analyzed
    (missing/empty/corrupt). Everything else is a warning: analysis proceeds,
    but extraction reliability is likely reduced.
    """

    usable: bool = True
    warnings: list = field(default_factory=list)


def check_screenshot_quality(image_path: Union[str, Path]) -> ScreenshotQuality:
    """Detect obvious quality limitations of a local screenshot file.

    Checks resolution and aspect ratio only — whether trade markup is actually
    visible can only be judged by the vision model itself, so that limitation
    is surfaced post-analysis (trade_overlay.source == "none"), not here.
    Fails open (no warnings) if Pillow is unavailable.
    """
    path = Path(image_path)
    if not path.exists() or path.stat().st_size == 0:
        return ScreenshotQuality(
            usable=False, warnings=["The image file is missing or empty."]
        )

    try:
        from PIL import Image
    except ImportError:  # pragma: no cover — Pillow is a hard app dependency
        return ScreenshotQuality()

    try:
        with Image.open(path) as img:
            width, height = img.size
    except Exception:  # noqa: BLE001 — any unreadable file is unusable
        return ScreenshotQuality(
            usable=False,
            warnings=["This file couldn't be read as an image — it may be corrupt."],
        )

    quality = ScreenshotQuality()
    if width < _MIN_WIDTH or height < _MIN_HEIGHT:
        quality.warnings.append(
            f"Low resolution ({width}×{height}) — price labels may be unreadable, "
            "so extracted values will be less reliable."
        )
    if height and (width / height > _MAX_ASPECT or height / width > _MAX_ASPECT):
        quality.warnings.append(
            "Unusual shape — the chart looks cropped, so the price scale or "
            "trade markup may be cut off."
        )
    return quality


def _fill_defaults(data: dict) -> dict:
    defaults = {
        "bias": None,
        "bias_confidence": None,
        "detected_timeframe": None,
        "detected_asset": None,
        "structure": None,
        "bos": None,
        "choch": None,
        "key_zones": [],
        "matched_strategy": None,
        "matched_strategy_reason": None,
        "possible_mistakes": [],
        "missed_opportunities": [],
        "trade_quality": None,
        "notes_to_user": None,
        "htf_bias": None,
        "liquidity_sweep": None,
        "fvg_used": None,
        "order_block_used": None,
    }
    return {**defaults, **{k: v for k, v in data.items() if k in _EXPECTED_KEYS}}


def analyze_screenshot(
    image_path: Union[str, Path],
    trade_ctx: dict,
    strategy_profile: Optional[dict] = None,
) -> tuple[dict, Usage]:
    """
    Analyze a post-trade chart screenshot using claude-fable-5 vision.

    Args:
        image_path: Path to the local chart image.
        trade_ctx: Dict of trade fields (asset, direction, result, pnl, etc.).
        strategy_profile: Optional strategy rules dict. Falls back to generic
                          ICT/SMC price-action analysis when None or empty.

    Returns:
        (analysis_dict, usage) where analysis_dict contains all 14 schema keys.

    Raises:
        ScreenshotAnalysisError: Missing image, unsupported type, or empty file.
        FileNotFoundError: Prompt template missing from prompts/.
        ScreenshotAnalysisError: API returned unparseable JSON.
    """
    path = Path(image_path)

    if not path.exists():
        raise ScreenshotAnalysisError(f"Image not found: {path}")

    if path.suffix.lower() not in _SUPPORTED_EXTENSIONS:
        raise ScreenshotAnalysisError(
            f"Unsupported file type '{path.suffix}'. "
            f"Allowed: {', '.join(sorted(_SUPPORTED_EXTENSIONS))}"
        )

    if path.stat().st_size == 0:
        raise ScreenshotAnalysisError(f"Image file is empty: {path}")

    system_message = load_prompt("screenshot_v2")

    if strategy_profile:
        strategy_block = json.dumps(strategy_profile, indent=2)
    else:
        strategy_block = (
            "No strategy profile provided — use generic price-action analysis."
        )

    user_message = (
        "POST-TRADE REVIEW\n\n"
        f"Trade context:\n{json.dumps(trade_ctx, indent=2, default=str)}\n\n"
        f"Strategy profile:\n{strategy_block}\n\n"
        "Analyze the chart screenshot above and return the JSON object as instructed."
    )

    # DEMO_MODE: serve a cached fixture (trade-keyed, then default) so the demo
    # renders real analysis with zero API spend. ai_client short-circuits on it.
    demo_resp = None
    if is_demo():
        demo_resp = (
            load_demo_fixture("vision", (trade_ctx or {}).get("id"))
            or '{"bias": "neutral", "trade_quality": 5}'
        )

    raw, usage = vision(
        image_path=path,
        user_message=user_message,
        system_message=system_message,
        response_format={"type": "json_object"},
        demo_response=demo_resp,
    )

    if isinstance(raw, AIUnavailable):
        raise ScreenshotAnalysisError(raw.reason)

    data = parse_ai_json(raw)
    return _fill_defaults(data), usage


# ---------------------------------------------------------------------------
# screenshot_v3 — descriptive context + visible trade-box overlay (Session F P3)
# ---------------------------------------------------------------------------

_DESCRIPTIVE_DEFAULTS = {
    "detected_asset": None,
    "instrument_name": None,
    "detected_timeframe": None,
    "htf_bias": None,
    "bias": None,
    "structure": None,
    "bos": None,
    "choch": None,
    "liquidity_sweep": None,
    "fvg_used": None,
    "order_block_used": None,
    "matched_strategy": None,
    "matched_strategy_reason": None,
    "trade_quality": None,
    "possible_mistakes": None,
    "missed_opportunities": None,
    "key_zones": [],
    "notes_to_user": None,
}
_OVERLAY_DEFAULTS = {
    "direction": None,
    "entry_price": None,
    "stop_price": None,
    "tp_price": None,
    "exit_price": None,
    "risk_reward_ratio": None,
    "pnl": None,
    "overall_confidence": None,
    "visible_labels": [],
    "confidence": {},
    "source": "none",
}

# Minimal valid v3 object for DEMO_MODE when no fixture exists (zero network).
_DEMO_V3 = '{"descriptive": {"bias": "neutral"}, "trade_overlay": {"source": "none"}}'


def _fill_defaults_v3(data: dict) -> dict:
    """Coerce a parsed v3 response into the two-section shape with safe defaults.

    Guarantees ``descriptive`` and ``trade_overlay`` are dicts with every key
    present, so downstream parsing (ai_overlay) never has to guard for shape.
    """
    data = data if isinstance(data, dict) else {}
    desc = data.get("descriptive")
    desc = desc if isinstance(desc, dict) else {}
    overlay = data.get("trade_overlay")
    overlay = overlay if isinstance(overlay, dict) else {}
    return {
        "descriptive": {**_DESCRIPTIVE_DEFAULTS, **desc},
        "trade_overlay": {**_OVERLAY_DEFAULTS, **overlay},
    }


def analyze_screenshot_v3(
    image_path: Union[str, Path],
    trade_ctx: dict,
    strategy_profile: Optional[dict] = None,
) -> tuple[dict, Usage]:
    """Post-trade screenshot analysis using the screenshot_v3 prompt.

    Returns (v3_dict, usage) where v3_dict has ``descriptive`` (chart context) and
    ``trade_overlay`` (visible trade-box geometry) sections. The v2 path
    (analyze_screenshot) is unchanged, so the existing Journal flow is untouched.
    """
    path = Path(image_path)

    if not path.exists():
        raise ScreenshotAnalysisError(f"Image not found: {path}")
    if path.suffix.lower() not in _SUPPORTED_EXTENSIONS:
        raise ScreenshotAnalysisError(
            f"Unsupported file type '{path.suffix}'. "
            f"Allowed: {', '.join(sorted(_SUPPORTED_EXTENSIONS))}"
        )
    if path.stat().st_size == 0:
        raise ScreenshotAnalysisError(f"Image file is empty: {path}")

    system_message = load_prompt("screenshot_v3")

    if strategy_profile:
        strategy_block = json.dumps(strategy_profile, indent=2)
    else:
        strategy_block = (
            "No strategy profile provided — use generic price-action analysis."
        )

    user_message = (
        "POST-TRADE REVIEW\n\n"
        f"Trade context:\n{json.dumps(trade_ctx, indent=2, default=str)}\n\n"
        f"Strategy profile:\n{strategy_block}\n\n"
        "Analyze the chart screenshot above and return the JSON object as instructed."
    )

    demo_resp = None
    if is_demo():
        demo_resp = (
            load_demo_fixture("vision_v3", (trade_ctx or {}).get("id")) or _DEMO_V3
        )

    raw, usage = vision(
        image_path=path,
        user_message=user_message,
        system_message=system_message,
        response_format={"type": "json_object"},
        demo_response=demo_resp,
    )

    if isinstance(raw, AIUnavailable):
        raise ScreenshotAnalysisError(raw.reason)

    return _fill_defaults_v3(parse_ai_json(raw)), usage
