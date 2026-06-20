"""
Tests for patterns.py — deterministic pre-pass is pure pandas; the single AI
call is always mocked (no network, no cost). DEMO_MODE path exercises the real
ai_client short-circuit.
"""

import json
from unittest.mock import patch

import pandas as pd
import pytest

from src.tradelens.services.ai_client import AIUnavailable, Usage


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

_CANDIDATE_DF = pd.DataFrame(
    {
        "trade_date": [
            "2025-01-01",
            "2025-01-02",
            "2025-01-03",
            "2025-01-04",
            "2025-01-05",
            "2025-01-06",
        ],
        "result": ["Win", "Loss", "Win", "Loss", "Win", "Loss"],
        "pnl": [200.0, -100.0, 150.0, -80.0, 90.0, -60.0],
        "killzone": ["ny_am", "ny_am", "london_open", "london_open", "ny_am", "asia"],
        "htf_bias": ["bullish", "bullish", "bearish", "bearish", "bullish", "bullish"],
        "setup_type": ["FVG", "FVG", "OB", "OB", "FVG", "OB"],
        "confirmation_model": ["BOS", "BOS", "CHoCH", "CHoCH", "BOS", "BOS"],
        "rr_realized": [2.0, -1.0, 1.5, -1.0, 1.0, -1.0],
        "mistake_tags": ["[]", '["FOMO"]', "[]", '["Late Entry"]', "[]", '["FOMO"]'],
        "followed_rules": [1, 0, 1, 0, 1, 0],
    }
)


def _make_usage() -> Usage:
    return Usage(
        model="claude-fable-5",
        tokens_in=500,
        tokens_out=700,
        total_tokens=1200,
        estimated_cost_usd=0.0005,
        latency_s=3.0,
    )


def _card(**over) -> dict:
    base = {
        "insight": "You overtrade the NY AM killzone right after a loss.",
        "evidence_stat": "Win rate drops to 22% on same-session re-entries.",
        "sample_size": 12,
        "confidence": "medium",
        "impact": "-$540 over the period",
        "suggested_rule": "No new entries within 15 minutes of a loss.",
    }
    base.update(over)
    return base


def _payload(cards) -> str:
    return json.dumps({"patterns": cards})


# ---------------------------------------------------------------------------
# compute_candidates — deterministic pandas pre-pass
# ---------------------------------------------------------------------------


def test_compute_candidates_returns_expected_keys():
    from src.tradelens.services.patterns import compute_candidates

    res = compute_candidates(_CANDIDATE_DF)
    expected = {
        "total_trades",
        "total_edge_leak",
        "streaks",
        "by_killzone",
        "by_confirmation_model",
        "by_bias",
        "by_setup_type",
        "mistake_clusters",
    }
    assert expected.issubset(res.keys())


def test_compute_candidates_total_trades_and_edge_leak():
    from src.tradelens.services.patterns import compute_candidates

    res = compute_candidates(_CANDIDATE_DF)
    assert res["total_trades"] == 6
    # rows 2,4,6 broke rules / carry mistakes: -100 + -80 + -60
    assert res["total_edge_leak"] == pytest.approx(-240.0)
    assert isinstance(res["by_killzone"], list) and res["by_killzone"]
    assert isinstance(res["streaks"], dict)


def test_compute_candidates_empty_df_is_safe():
    from src.tradelens.services.patterns import compute_candidates

    res = compute_candidates(pd.DataFrame())
    assert res["total_trades"] == 0
    assert res["total_edge_leak"] == pytest.approx(0.0)
    assert res["by_killzone"] == []
    assert res["mistake_clusters"] == []


# ---------------------------------------------------------------------------
# generate_cards — single mocked AI call
# ---------------------------------------------------------------------------


def test_generate_cards_parses_valid_json():
    from src.tradelens.services.patterns import generate_cards

    payload = _payload([_card(), _card(insight="London open underperforms.")])
    with patch(
        "src.tradelens.services.patterns.chat", return_value=(payload, _make_usage())
    ), patch("src.tradelens.services.patterns.load_prompt", return_value="mock"):
        cards, usage = generate_cards({"total_trades": 6})

    assert isinstance(cards, list)
    assert len(cards) == 2
    assert cards[0]["insight"].startswith("You overtrade")
    assert usage.model == "claude-fable-5"


def test_generate_cards_caps_at_six():
    from src.tradelens.services.patterns import generate_cards

    payload = _payload([_card(insight=f"Pattern {i}") for i in range(8)])
    with patch(
        "src.tradelens.services.patterns.chat", return_value=(payload, _make_usage())
    ), patch("src.tradelens.services.patterns.load_prompt", return_value="mock"):
        cards, _ = generate_cards({"total_trades": 6})

    assert len(cards) == 6


def test_generate_cards_low_sample_labeling():
    from src.tradelens.services.patterns import LOW_SAMPLE_LABEL, generate_cards

    payload = _payload([_card(sample_size=3), _card(sample_size=10)])
    with patch(
        "src.tradelens.services.patterns.chat", return_value=(payload, _make_usage())
    ), patch("src.tradelens.services.patterns.load_prompt", return_value="mock"):
        cards, _ = generate_cards({"total_trades": 6})

    assert cards[0]["low_sample"] is True
    assert cards[0]["sample_label"] == LOW_SAMPLE_LABEL
    assert cards[1]["low_sample"] is False
    assert cards[1]["sample_label"] is None


def test_generate_cards_missing_key_raises():
    from src.tradelens.services.patterns import PatternError, generate_cards

    bad = _card()
    del bad["suggested_rule"]
    payload = _payload([bad])
    with patch(
        "src.tradelens.services.patterns.chat", return_value=(payload, _make_usage())
    ), patch("src.tradelens.services.patterns.load_prompt", return_value="mock"):
        with pytest.raises(PatternError, match="suggested_rule"):
            generate_cards({"total_trades": 6})


def test_generate_cards_invalid_json_raises():
    from src.tradelens.services.ai_client import AIParseError
    from src.tradelens.services.patterns import generate_cards

    with patch(
        "src.tradelens.services.patterns.chat",
        return_value=("not json at all", _make_usage()),
    ), patch("src.tradelens.services.patterns.load_prompt", return_value="mock"):
        with pytest.raises(AIParseError, match="JSON"):
            generate_cards({"total_trades": 6})


def test_generate_cards_ai_unavailable_raises():
    from src.tradelens.services.patterns import PatternError, generate_cards

    with patch(
        "src.tradelens.services.patterns.chat",
        return_value=(AIUnavailable("AI declined"), _make_usage()),
    ), patch("src.tradelens.services.patterns.load_prompt", return_value="mock"):
        with pytest.raises(PatternError, match="AI declined"):
            generate_cards({"total_trades": 6})


def test_generate_cards_demo_mode_returns_canned(monkeypatch):
    """DEMO_MODE returns canned cards through the real ai_client short-circuit."""
    import src.tradelens.services.ai_client as ai_client
    from src.tradelens.services.patterns import generate_cards

    monkeypatch.setattr(ai_client.settings, "demo_mode", True)

    cards, usage = generate_cards({"total_trades": 6})

    assert isinstance(cards, list) and len(cards) >= 1
    for card in cards:
        assert {
            "insight",
            "evidence_stat",
            "sample_size",
            "confidence",
            "impact",
            "suggested_rule",
        }.issubset(card.keys())
    assert usage.estimated_cost_usd == 0.0  # no spend
