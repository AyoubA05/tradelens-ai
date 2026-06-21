"""
Post-trade screenshot analysis service.

Calls claude-fable-5 vision to review a chart image AFTER a trade has closed.
This is educational journaling only — not live trading advice.
"""

import json
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
