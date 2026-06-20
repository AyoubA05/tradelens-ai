"""
Post-trade journal generation service.

Generates an 8-section markdown journal entry using user-confirmed AI labels
and trade data. This is educational reflection only — not live trading advice.
"""

import json
from typing import Optional

from src.tradelens.services.ai_client import AIUnavailable, Usage, chat, load_prompt

_REQUIRED_SECTIONS = [
    "### Trade Summary",
    "### Market Bias",
    "### Strategy Used",
    "### What Went Well",
    "### What Went Wrong",
    "### Missed Opportunities",
    "### Emotional Review",
    "### Improvement Plan",
]

_GENERIC_STRATEGY_FALLBACK = (
    "No strategy profile provided. Apply a generic price-action / ICT framework:\n"
    "• Entry: Order block retest, FVG fill, or liquidity sweep with BOS/CHoCH confirmation\n"
    "• Stop: Behind entry candle high/low or the nearest key zone\n"
    "• Take Profit: Next liquidity area, opposing OB, or key S/R level\n"
    "• Risk: 1–2% per trade, minimum 1:2 R:R"
)


class JournalStructureError(Exception):
    """Raised when the AI response is missing required H3 sections."""


def _validate_journal_sections(markdown: str) -> None:
    """
    Verify all 8 required H3 headings are present and in the correct order.
    Raises JournalStructureError with a descriptive message if not.
    """
    positions = []
    for section in _REQUIRED_SECTIONS:
        idx = markdown.find(section)
        if idx == -1:
            raise JournalStructureError(
                f"Journal is missing required section: '{section}'"
            )
        positions.append(idx)

    if positions != sorted(positions):
        out_of_order = []
        for i, (pos, section) in enumerate(zip(positions, _REQUIRED_SECTIONS)):
            if i > 0 and pos < positions[i - 1]:
                out_of_order.append(section)
        raise JournalStructureError(
            f"Journal sections are out of order. Check: {out_of_order}"
        )


def build_journal_context(trade, analysis) -> tuple[dict, dict]:
    """
    Extract and deserialize all data needed for generate_journal() from ORM objects.

    Keeps Streamlit pages thin — they call this helper instead of building dicts inline.
    Returns (trade_dict, ai_analysis_dict).
    """
    trade_dict = {
        "asset": trade.asset,
        "direction": trade.direction,
        "result": trade.result,
        "pnl": trade.pnl,
        "rr_realized": trade.rr_realized,
        "session": trade.session,
        "setup_type": trade.setup_type,
        "bias": trade.bias,
        "emotions_before": trade.emotions_before,
        "emotions_during": trade.emotions_during,
        "emotions_after": trade.emotions_after,
        "notes": trade.notes,
        "strategy_used": trade.strategy_used,
        "trade_date": trade.trade_date,
    }

    try:
        key_zones = json.loads(analysis.zones_json or "[]")
    except (json.JSONDecodeError, TypeError):
        key_zones = []

    try:
        possible_mistakes = json.loads(analysis.mistakes_json or "[]")
    except (json.JSONDecodeError, TypeError):
        possible_mistakes = []

    try:
        missed_opportunities = json.loads(analysis.missed_opps_json or "[]")
    except (json.JSONDecodeError, TypeError):
        missed_opportunities = []

    ai_analysis_dict = {
        "bias": analysis.bias,
        "detected_setup": analysis.detected_setup,
        "trade_quality": analysis.trade_quality,
        "matched_strategy": analysis.matched_strategy,
        "key_zones": key_zones,
        "possible_mistakes": possible_mistakes,
        "missed_opportunities": missed_opportunities,
    }

    return trade_dict, ai_analysis_dict


def generate_journal(
    trade: dict,
    ai_analysis: dict,
    strategy_profile: Optional[dict] = None,
) -> tuple[str, Usage]:
    """
    Generate an 8-section markdown journal entry for a closed post-trade review.

    Args:
        trade: Trade fields (asset, direction, result, pnl, emotions, notes, etc.).
        ai_analysis: User-confirmed AI labels (bias, setup, quality, mistakes, etc.).
        strategy_profile: Optional strategy rules dict; falls back to generic ICT framework.

    Returns:
        (markdown_str, usage)

    Raises:
        FileNotFoundError: If prompts/journal_v1.txt is missing.
        JournalStructureError: If AI response is missing required H3 sections.
    """
    system_message = load_prompt("journal_v1")

    if strategy_profile:
        strategy_block = json.dumps(strategy_profile, indent=2, default=str)
    else:
        strategy_block = _GENERIC_STRATEGY_FALLBACK

    user_message = (
        "POST-TRADE JOURNAL REQUEST\n\n"
        f"Trade data:\n{json.dumps(trade, indent=2, default=str)}\n\n"
        f"AI analysis labels (user-confirmed):\n{json.dumps(ai_analysis, indent=2, default=str)}\n\n"
        f"Strategy profile:\n{strategy_block}\n\n"
        "Write the 8-section journal entry now."
    )

    content, usage = chat(
        user_message=user_message,
        system_message=system_message,
    )

    if isinstance(content, AIUnavailable):
        raise JournalStructureError(content.reason)

    _validate_journal_sections(content)
    return content, usage
