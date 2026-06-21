"""
Post-trade grading service.

Scores a trade on PROCESS (not outcome) across 5 dimensions using claude-haiku-4-5.
This is educational review only — not live trading advice.
"""

import json
from typing import Optional

from src.tradelens.config import settings
from src.tradelens.services.ai_client import (
    AIUnavailable,
    Usage,
    chat,
    load_prompt,
    parse_ai_json,
)
from src.tradelens.services.demo import is_demo, load_demo_fixture

# Minimal valid grading response used in DEMO_MODE if the fixture file is absent.
_DEMO_GRADE_FALLBACK = json.dumps(
    {
        "grade": "B",
        "score": 7,
        "one_line_verdict": "Solid, disciplined execution.",
        "rubric": {
            "entry_quality": {"score": 7, "note": "Reasonable entry on the retest."},
            "risk_management": {"score": 8, "note": "Risk defined and controlled."},
            "exit_quality": {"score": 7, "note": "Acceptable exit management."},
            "rule_adherence": {"score": 8, "note": "Followed the plan."},
            "emotional_control": {"score": 8, "note": "Calm and patient."},
        },
    }
)

_REQUIRED_TOP_KEYS = {"grade", "score", "rubric", "one_line_verdict"}
_REQUIRED_RUBRIC_DIMS = {
    "entry_quality",
    "risk_management",
    "exit_quality",
    "rule_adherence",
    "emotional_control",
}

_GENERIC_STRATEGY_FALLBACK = (
    "No strategy profile provided. Grade against generic ICT/price-action principles:\n"
    "• Stop loss must be defined before entry\n"
    "• Position size must keep risk below 2% of account\n"
    "• Entry trigger must be confirmed (BOS, CHoCH, OB retest, FVG fill, etc.)\n"
    "• Minimum 1:1 R:R required; 1:2 preferred\n"
    "• No trading against the higher timeframe bias"
)


class GradingError(Exception):
    """Raised when the AI grading response is missing required fields."""


def _validate_grading_result(data: dict) -> None:
    """
    Validate top-level keys AND all 5 rubric dimensions with score+note.
    Raises GradingError with a descriptive message on any violation.
    """
    missing_top = _REQUIRED_TOP_KEYS - data.keys()
    if missing_top:
        raise GradingError(f"Grading response missing top-level keys: {missing_top}")

    rubric = data.get("rubric", {})
    if not isinstance(rubric, dict):
        raise GradingError("Grading response 'rubric' must be a JSON object.")

    missing_dims = _REQUIRED_RUBRIC_DIMS - rubric.keys()
    if missing_dims:
        raise GradingError(f"Rubric missing required dimensions: {missing_dims}")

    for dim in _REQUIRED_RUBRIC_DIMS:
        entry = rubric[dim]
        if not isinstance(entry, dict):
            raise GradingError(f"Rubric dimension '{dim}' must be a JSON object.")
        missing_fields = {"score", "note"} - entry.keys()
        if missing_fields:
            raise GradingError(
                f"Rubric dimension '{dim}' missing fields: {missing_fields}"
            )


def build_grading_context(trade, analysis) -> tuple[dict, dict]:
    """
    Convert ORM objects to plain dicts ready for grade_trade().
    Keeps Streamlit pages thin — call this helper instead of building dicts inline.
    Returns (trade_dict, vision_dict).
    """
    trade_dict = {
        "asset": trade.asset,
        "direction": trade.direction,
        "result": trade.result,
        "pnl": trade.pnl,
        "rr_realized": trade.rr_realized,
        "rr_planned": trade.rr_planned,
        "session": trade.session,
        "setup_type": trade.setup_type,
        "bias": trade.bias,
        "entry_price": trade.entry_price,
        "stop_price": trade.stop_price,
        "exit_price": trade.exit_price,
        "position_size": trade.position_size,
        "risk_amount": trade.risk_amount,
        "emotions_before": trade.emotions_before,
        "emotions_during": trade.emotions_during,
        "emotions_after": trade.emotions_after,
        "notes": trade.notes,
        "strategy_used": trade.strategy_used,
    }

    try:
        possible_mistakes = json.loads(analysis.mistakes_json or "[]")
    except (json.JSONDecodeError, TypeError):
        possible_mistakes = []

    try:
        missed_opportunities = json.loads(analysis.missed_opps_json or "[]")
    except (json.JSONDecodeError, TypeError):
        missed_opportunities = []

    vision_dict = {
        "bias": analysis.bias,
        "detected_setup": analysis.detected_setup,
        "trade_quality": analysis.trade_quality,
        "matched_strategy": analysis.matched_strategy,
        "possible_mistakes": possible_mistakes,
        "missed_opportunities": missed_opportunities,
    }

    return trade_dict, vision_dict


def grade_trade(
    trade: dict,
    strategy_profile: Optional[dict],
    vision_analysis: dict,
) -> tuple[dict, Usage]:
    """
    Grade a closed trade on PROCESS using claude-haiku-4-5.

    Args:
        trade: Trade fields (asset, direction, result, prices, emotions, notes, etc.).
        strategy_profile: Optional strategy rules dict; falls back to generic ICT principles.
        vision_analysis: User-confirmed AI labels (bias, setup, mistakes, etc.).

    Returns:
        (grading_dict, usage) — grading_dict has grade, score, rubric, one_line_verdict.

    Raises:
        FileNotFoundError: If prompts/grade_v1.txt is missing.
        GradingError: If AI response is missing required keys or rubric dimensions.
    """
    system_message = load_prompt("grade_v1")

    if strategy_profile:
        strategy_block = json.dumps(strategy_profile, indent=2, default=str)
    else:
        strategy_block = _GENERIC_STRATEGY_FALLBACK

    user_message = (
        "POST-TRADE GRADING REQUEST\n\n"
        f"Trade data:\n{json.dumps(trade, indent=2, default=str)}\n\n"
        f"AI analysis (user-confirmed labels):\n{json.dumps(vision_analysis, indent=2, default=str)}\n\n"
        f"Strategy profile:\n{strategy_block}\n\n"
        "Grade this trade on process. Return the JSON grading object now."
    )

    # DEMO_MODE: serve a cached grading fixture (zero API spend).
    demo_resp = None
    if is_demo():
        demo_resp = load_demo_fixture("grade", trade.get("id")) or _DEMO_GRADE_FALLBACK

    content, usage = chat(
        user_message=user_message,
        system_message=system_message,
        model=settings.model_grading,
        response_format={"type": "json_object"},
        demo_response=demo_resp,
    )

    if isinstance(content, AIUnavailable):
        raise GradingError(content.reason)

    data = parse_ai_json(content)
    _validate_grading_result(data)
    return data, usage
