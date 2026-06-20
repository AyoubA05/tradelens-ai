"""
Pattern detection service.

Two stages, deliberately separated so the deterministic math is unit-testable
and the single AI call is trivial to mock:

  1. compute_candidates(trades) — pure-pandas pre-pass built on already-tested
     metrics (killzone / bias / setup / confirmation-model breakdowns, streaks,
     mistake clusters, rule-violation cost). No AI, no Streamlit.
  2. generate_cards(candidates) — one claude-fable-5 call via ai_client using
     prompts/patterns_v2.txt → at most 6 strict-JSON pattern cards.

This is post-trade reflection only. Cards describe what already happened and
suggest process rules to consider — never live signals, predictions, or advice.
"""

import json

import pandas as pd

from src.tradelens.services.ai_client import (
    AIUnavailable,
    Usage,
    chat,
    load_prompt,
    parse_ai_json,
)
from src.tradelens.services.metrics import (
    compute_breakdown,
    compute_streaks,
    confirmation_model_performance,
    killzone_performance,
    mistake_frequency,
    total_edge_leak,
)

MAX_CARDS = 6
LOW_SAMPLE_THRESHOLD = 5
LOW_SAMPLE_LABEL = "early signal — low sample"

_REQUIRED_CARD_KEYS = {
    "insight",
    "evidence_stat",
    "sample_size",
    "confidence",
    "impact",
    "suggested_rule",
}

# Canned cards returned in DEMO_MODE (zero spend) — mirrors the real contract.
_DEMO_CARDS_JSON = json.dumps(
    {
        "patterns": [
            {
                "insight": "Trades taken after a loss in the same session underperform.",
                "evidence_stat": "Win rate falls from 58% to 24% on same-session re-entries.",
                "sample_size": 11,
                "confidence": "medium",
                "impact": "-$430 over the period",
                "suggested_rule": "Step away for 15 minutes after any loss before re-entering.",
            },
            {
                "insight": "Skipping the higher-timeframe bias check correlates with losses.",
                "evidence_stat": "8 of 10 rule-break trades had no HTF bias logged.",
                "sample_size": 10,
                "confidence": "medium",
                "impact": "-$310 over the period",
                "suggested_rule": "Confirm and log HTF bias before every entry.",
            },
        ]
    }
)


class PatternError(Exception):
    """Raised when the AI pattern response is missing, malformed, or invalid JSON."""


def compute_candidates(trades: pd.DataFrame) -> dict:
    """
    Deterministic pre-pass bundling the signals the AI reasons over.

    Reuses already-tested metrics helpers so the numbers here match the rest of
    the dashboard exactly. Returns a plain JSON-serialisable dict — no AI call.
    Empty / None input yields a zeroed structure rather than raising.
    """
    if trades is None or trades.empty:
        return {
            "total_trades": 0,
            "total_edge_leak": 0.0,
            "streaks": compute_streaks(pd.DataFrame()),
            "by_killzone": [],
            "by_confirmation_model": [],
            "by_bias": [],
            "by_setup_type": [],
            "mistake_clusters": [],
        }

    return {
        "total_trades": int(len(trades)),
        "total_edge_leak": total_edge_leak(trades),
        "streaks": compute_streaks(trades),
        "by_killzone": killzone_performance(trades).to_dict("records"),
        "by_confirmation_model": confirmation_model_performance(trades).to_dict(
            "records"
        ),
        "by_bias": compute_breakdown(trades, "htf_bias").to_dict("records"),
        "by_setup_type": compute_breakdown(trades, "setup_type").to_dict("records"),
        "mistake_clusters": mistake_frequency(trades).to_dict("records"),
    }


def _parse_cards(content: str) -> list:
    """
    Parse the AI response into a list of card dicts.

    Tolerates a ```json fence and accepts either a {"patterns": [...]} object or
    a bare list. Raises PatternError on anything that is not valid JSON.
    """
    data = parse_ai_json(content)

    if isinstance(data, dict):
        cards = data.get("patterns", [])
    elif isinstance(data, list):
        cards = data
    else:
        raise PatternError("Pattern response JSON must be an object or a list.")

    if not isinstance(cards, list):
        raise PatternError("Pattern response 'patterns' must be a JSON list.")
    return cards


def _validate_and_label(cards: list) -> list:
    """Validate required keys, cap to MAX_CARDS, and annotate low-sample cards."""
    validated = []
    for card in cards[:MAX_CARDS]:
        if not isinstance(card, dict):
            raise PatternError("Each pattern card must be a JSON object.")
        missing = _REQUIRED_CARD_KEYS - card.keys()
        if missing:
            raise PatternError(f"Pattern card missing required keys: {missing}")

        try:
            sample_size = int(card.get("sample_size"))
        except (TypeError, ValueError):
            sample_size = 0

        low_sample = sample_size < LOW_SAMPLE_THRESHOLD
        card["low_sample"] = low_sample
        card["sample_label"] = LOW_SAMPLE_LABEL if low_sample else None
        validated.append(card)
    return validated


def generate_cards(candidates: dict) -> tuple[list, Usage]:
    """
    Turn deterministic candidate stats into at most 6 strict-JSON pattern cards
    via a single claude-fable-5 call. DEMO_MODE returns canned cards (zero spend).

    Raises:
        FileNotFoundError: prompts/patterns_v2.txt missing.
        PatternError: AI unavailable, invalid JSON, or a card missing required keys.
    """
    system_message = load_prompt("patterns_v2")
    user_message = (
        "TRADE PATTERN ANALYSIS REQUEST\n\n"
        "Deterministic statistics computed from the trader's journal:\n"
        f"{json.dumps(candidates, indent=2, default=str)}\n\n"
        "Return the JSON pattern object now."
    )

    content, usage = chat(
        user_message=user_message,
        system_message=system_message,
        response_format={"type": "json_object"},
        demo_response=_DEMO_CARDS_JSON,
    )

    if isinstance(content, AIUnavailable):
        raise PatternError(content.reason)

    cards = _parse_cards(content)
    return _validate_and_label(cards), usage


def detect_patterns(trades: pd.DataFrame) -> tuple[list, Usage]:
    """Convenience orchestrator for pages: compute_candidates → generate_cards."""
    return generate_cards(compute_candidates(trades))
