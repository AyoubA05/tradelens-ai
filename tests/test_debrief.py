"""
Tests for debrief.py — daily session debrief + multi-trade summary service.
All AI calls are mocked (no network/cost); DEMO_MODE test uses the real
ai_client short-circuit.
"""

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from src.tradelens.services.ai_client import AIUnavailable, Usage

_REQUIRED_SECTIONS = [
    "### Session Summary",
    "### Discipline & Rule Adherence",
    "### Emotional Review",
    "### Recurring Patterns",
    "### Improvement Actions",
]


def _trade(**kw):
    base = {
        "trade_date": "2026-07-01",
        "day_of_week": "Wednesday",
        "asset": "MNQ",
        "direction": "Long",
        "timeframe": "1m",
        "session": "New York",
        "killzone": "ny_am",
        "setup_type": "FVG",
        "confirmation_model": "1m IFVG",
        "htf_bias": "bullish",
        "result": "Win",
        "pnl": 150.0,
        "rr_realized": 2.0,
        "followed_rules": 1,
        "mistake_tags": "[]",
        "emotions_before": "Calm",
        "emotions_during": "Focused",
        "emotions_after": None,
        "ai_grade": "B",
        "user_grade": None,
        "notes": None,
    }
    base.update(kw)
    return SimpleNamespace(**base)


def _full_debrief() -> str:
    return "\n\n".join(f"{h}\n\nSample content." for h in _REQUIRED_SECTIONS)


def _usage(cost=0.008) -> Usage:
    return Usage(
        model="claude-fable-5",
        tokens_in=1500,
        tokens_out=900,
        total_tokens=2400,
        estimated_cost_usd=cost,
        latency_s=5.0,
        thinking_summary="Weighed rule adherence against outcomes.",
    )


# ---------------------------------------------------------------------------
# build_trades_payload
# ---------------------------------------------------------------------------


def test_payload_parses_mistake_tags_and_orders_oldest_first():
    from src.tradelens.services.debrief import build_trades_payload

    trades = [
        _trade(trade_date="2026-07-02", mistake_tags='["FOMO Entry"]'),
        _trade(trade_date="2026-07-01"),
    ]
    payload = build_trades_payload(trades)
    assert [p["trade_date"] for p in payload] == ["2026-07-01", "2026-07-02"]
    assert payload[1]["mistake_tags"] == ["FOMO Entry"]
    assert payload[0]["mistake_tags"] == []


def test_payload_caps_at_40_newest_trades():
    from src.tradelens.services.debrief import build_trades_payload

    trades = [_trade(trade_date=f"2026-06-{d:02d}") for d in range(1, 31)]
    trades += [_trade(trade_date=f"2026-07-{d:02d}") for d in range(1, 21)]
    payload = build_trades_payload(trades)
    assert len(payload) == 40
    assert payload[-1]["trade_date"] == "2026-07-20"  # newest kept
    assert payload[0]["trade_date"] == "2026-06-11"  # oldest 10 dropped


def test_payload_truncates_long_notes_and_skips_empty():
    from src.tradelens.services.debrief import build_trades_payload

    long_note = "x" * 1000
    payload = build_trades_payload(
        [_trade(notes=long_note), _trade(notes="  "), _trade()]
    )
    assert len(payload[0]["notes"]) == 200
    assert "notes" not in payload[1]
    assert "notes" not in payload[2]


def test_payload_junk_mistake_tags_fail_safe():
    from src.tradelens.services.debrief import build_trades_payload

    payload = build_trades_payload([_trade(mistake_tags="not json")])
    assert payload[0]["mistake_tags"] == []


# ---------------------------------------------------------------------------
# generate_debrief
# ---------------------------------------------------------------------------


def test_empty_trades_makes_no_api_call():
    from src.tradelens.services.debrief import generate_debrief

    with patch("src.tradelens.services.debrief.chat") as mock_chat:
        review, usage = generate_debrief([])

    mock_chat.assert_not_called()
    assert review["empty"] is True
    assert review["content_md"] is None
    assert usage.estimated_cost_usd == 0.0


def test_generate_returns_sections_and_stats():
    from src.tradelens.services.debrief import generate_debrief

    captured = {}

    def fake_chat(user_message, system_message="", **kwargs):
        captured["user"] = user_message
        return _full_debrief(), _usage()

    with patch("src.tradelens.services.debrief.chat", side_effect=fake_chat), patch(
        "src.tradelens.services.debrief.load_prompt", return_value="mock"
    ):
        review, usage = generate_debrief(
            [_trade(), _trade(result="Loss", pnl=-75.0, followed_rules=0)],
            period_label="Trading day 2026-07-01",
        )

    assert review["empty"] is False
    for section in _REQUIRED_SECTIONS:
        assert section in review["content_md"]
    assert review["stats"]["trades"] == 2
    assert "Trading day 2026-07-01" in captured["user"]


def test_generate_includes_strategy_profile_when_present():
    from src.tradelens.services.debrief import generate_debrief

    captured = {}

    def fake_chat(user_message, system_message="", **kwargs):
        captured["user"] = user_message
        return _full_debrief(), _usage()

    with patch("src.tradelens.services.debrief.chat", side_effect=fake_chat), patch(
        "src.tradelens.services.debrief.load_prompt", return_value="mock"
    ):
        generate_debrief([_trade()], strategy_profile={"name": "London FVG"})

    assert "London FVG" in captured["user"]


def test_generate_falls_back_to_general_framework_without_profile():
    from src.tradelens.services.debrief import generate_debrief

    captured = {}

    def fake_chat(user_message, system_message="", **kwargs):
        captured["user"] = user_message
        return _full_debrief(), _usage()

    with patch("src.tradelens.services.debrief.chat", side_effect=fake_chat), patch(
        "src.tradelens.services.debrief.load_prompt", return_value="mock"
    ):
        generate_debrief([_trade()])

    assert "general review framework" in captured["user"]


def test_generate_missing_section_raises():
    from src.tradelens.services.debrief import DebriefError, generate_debrief

    incomplete = "### Session Summary\n\nOK"
    with patch(
        "src.tradelens.services.debrief.chat", return_value=(incomplete, _usage())
    ), patch("src.tradelens.services.debrief.load_prompt", return_value="mock"):
        with pytest.raises(DebriefError, match="missing required section"):
            generate_debrief([_trade()])


def test_generate_ai_unavailable_raises():
    from src.tradelens.services.debrief import DebriefError, generate_debrief

    with patch(
        "src.tradelens.services.debrief.chat",
        return_value=(AIUnavailable("no key"), _usage(cost=0.0)),
    ), patch("src.tradelens.services.debrief.load_prompt", return_value="mock"):
        with pytest.raises(DebriefError, match="no key"):
            generate_debrief([_trade()])


def test_generate_demo_mode_returns_canned_debrief(monkeypatch):
    import src.tradelens.services.ai_client as ai_client
    from src.tradelens.services.debrief import generate_debrief

    monkeypatch.setattr(ai_client.settings, "demo_mode", True)
    monkeypatch.setattr(
        ai_client, "build_correction_few_shot", lambda **k: "", raising=False
    )

    review, usage = generate_debrief([_trade()])

    assert review["empty"] is False
    for section in _REQUIRED_SECTIONS:
        assert section in review["content_md"]
    assert usage.estimated_cost_usd == 0.0


# ---------------------------------------------------------------------------
# Live UI wiring contracts (source-level, matching test_insights_page.py style)
# ---------------------------------------------------------------------------

_PAGES = Path(__file__).resolve().parents[1] / "src" / "tradelens" / "ui" / "pages"


def test_daily_debrief_is_wired_into_insights_page():
    src = (_PAGES / "6_Insights.py").read_text(encoding="utf-8")
    assert "Daily Debrief" in src
    assert "generate_debrief(" in src
    assert 'log_ai_usage("Daily Debrief"' in src  # cost stays truthful
    assert "strategy_profile=_strategy" in src  # strategy-aware


def test_multi_trade_summary_is_wired_into_journal_page():
    src = (_PAGES / "2_Trades.py").read_text(encoding="utf-8")
    assert "AI summary of these" in src
    assert "generate_debrief(" in src
    assert "log_ai_usage(" in src and '"Trade Summary"' in src
    assert "never signals" in src  # reflective framing


def test_weekly_review_call_is_user_scoped_and_strategy_aware():
    src = (_PAGES / "6_Insights.py").read_text(encoding="utf-8")
    assert src.count("generate_weekly_review(\n") == 2  # both call sites wrapped
    assert "user_id=uid, strategy_profile=_strategy" in src


def test_ai_available_gate_covers_demo(monkeypatch):
    import src.tradelens.utils.ai_utils as ai_utils

    monkeypatch.setattr(ai_utils, "is_ai_enabled", lambda: False)
    monkeypatch.setattr(
        "src.tradelens.services.demo.is_demo", lambda: True, raising=True
    )
    assert ai_utils.ai_available() is True

    monkeypatch.setattr("src.tradelens.services.demo.is_demo", lambda: False)
    assert ai_utils.ai_available() is False
