"""
Tests for weekly.py — AI calls are mocked (no network/cost); the DEMO_MODE test
exercises the real ai_client short-circuit. DB tests use in-memory SQLite.
"""

import datetime as dt
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.tradelens.db.models import Base
from src.tradelens.services.ai_client import AIUnavailable, Usage


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


@pytest.fixture()
def in_memory_db(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr("src.tradelens.services.weekly.SessionLocal", TestSession)
    return TestSession


def _fake_trades():
    return [
        SimpleNamespace(
            trade_date="2026-06-15",
            day_of_week="Monday",
            result="Win",
            pnl=200.0,
            rr_realized=2.0,
            killzone="ny_am",
            confirmation_model="BOS",
            mistake_tags="[]",
            htf_bias="bullish",
            setup_type="FVG",
            followed_rules=1,
        ),
        SimpleNamespace(
            trade_date="2026-06-17",
            day_of_week="Wednesday",
            result="Loss",
            pnl=-100.0,
            rr_realized=-1.0,
            killzone="ny_am",
            confirmation_model="BOS",
            mistake_tags='["FOMO"]',
            htf_bias="bullish",
            setup_type="FVG",
            followed_rules=0,
        ),
    ]


_REQUIRED_SECTIONS = [
    "### What Worked",
    "### What Didn't",
    "### Observed Patterns",
    "### Rule Adherence",
    "### Focus for Next Week",
]


def _full_review() -> str:
    return "\n\n".join(f"{h}\n\nSample content." for h in _REQUIRED_SECTIONS)


def _make_usage(cost=0.012, thinking="I weighed killzone win rates.") -> Usage:
    return Usage(
        model="claude-fable-5",
        tokens_in=2000,
        tokens_out=1200,
        total_tokens=3200,
        estimated_cost_usd=cost,
        latency_s=8.0,
        thinking_summary=thinking,
    )


# ---------------------------------------------------------------------------
# week_bounds — Monday→Sunday window selection
# ---------------------------------------------------------------------------


def test_week_bounds_from_midweek_date():
    from src.tradelens.services.weekly import week_bounds

    assert week_bounds(dt.date(2026, 6, 17)) == ("2026-06-15", "2026-06-21")


def test_week_bounds_on_monday_and_sunday_edges():
    from src.tradelens.services.weekly import week_bounds

    assert week_bounds(dt.date(2026, 6, 15)) == ("2026-06-15", "2026-06-21")
    assert week_bounds(dt.date(2026, 6, 21)) == ("2026-06-15", "2026-06-21")


def test_week_bounds_accepts_iso_string():
    from src.tradelens.services.weekly import week_bounds

    assert week_bounds("2026-06-19") == ("2026-06-15", "2026-06-21")


# ---------------------------------------------------------------------------
# generate_weekly_review
# ---------------------------------------------------------------------------


def test_zero_trade_week_makes_no_api_call():
    from src.tradelens.services.weekly import generate_weekly_review

    with patch("src.tradelens.services.weekly.get_trades", return_value=[]), patch(
        "src.tradelens.services.weekly.chat"
    ) as mock_chat:
        review, usage = generate_weekly_review("2026-06-17", user_id=1)

    mock_chat.assert_not_called()
    assert review["empty"] is True
    assert review["content_md"] is None
    assert review["week_start"] == "2026-06-15"
    assert usage.estimated_cost_usd == 0.0


def test_generate_uses_high_effort_and_returns_sections():
    from src.tradelens.services.weekly import generate_weekly_review

    captured = {}

    def fake_chat(user_message, system_message="", **kwargs):
        captured.update(kwargs)
        captured["user"] = user_message
        return _full_review(), _make_usage()

    with patch(
        "src.tradelens.services.weekly.get_trades", return_value=_fake_trades()
    ), patch("src.tradelens.services.weekly.chat", side_effect=fake_chat), patch(
        "src.tradelens.services.weekly.load_prompt", return_value="mock"
    ):
        review, usage = generate_weekly_review("2026-06-17", user_id=1)

    assert captured["effort"] == "high"
    assert review["empty"] is False
    for section in _REQUIRED_SECTIONS:
        assert section in review["content_md"]
    assert review["thinking_summary"] == "I weighed killzone win rates."
    assert review["stats"]["trades"] == 2


def test_generate_missing_section_raises():
    from src.tradelens.services.weekly import WeeklyReviewError, generate_weekly_review

    incomplete = "### What Worked\n\nOK\n\n### What Didn't\n\nOK"  # only 2 of 5
    with patch(
        "src.tradelens.services.weekly.get_trades", return_value=_fake_trades()
    ), patch(
        "src.tradelens.services.weekly.chat", return_value=(incomplete, _make_usage())
    ), patch(
        "src.tradelens.services.weekly.load_prompt", return_value="mock"
    ):
        with pytest.raises(WeeklyReviewError, match="missing required section"):
            generate_weekly_review("2026-06-17", user_id=1)


def test_generate_ai_unavailable_raises():
    from src.tradelens.services.weekly import WeeklyReviewError, generate_weekly_review

    with patch(
        "src.tradelens.services.weekly.get_trades", return_value=_fake_trades()
    ), patch(
        "src.tradelens.services.weekly.chat",
        return_value=(AIUnavailable("AI declined"), _make_usage()),
    ), patch(
        "src.tradelens.services.weekly.load_prompt", return_value="mock"
    ):
        with pytest.raises(WeeklyReviewError, match="AI declined"):
            generate_weekly_review("2026-06-17", user_id=1)


def test_generate_demo_mode_returns_mock_review(monkeypatch):
    """DEMO_MODE returns the canned 5-section review via the real ai_client path."""
    import src.tradelens.services.ai_client as ai_client
    from src.tradelens.services.weekly import generate_weekly_review

    monkeypatch.setattr(ai_client.settings, "demo_mode", True)
    # corrections are injected centrally now — keep this hermetic
    monkeypatch.setattr(
        ai_client, "build_correction_few_shot", lambda **k: "", raising=False
    )

    with patch("src.tradelens.services.weekly.get_trades", return_value=_fake_trades()):
        review, usage = generate_weekly_review("2026-06-17", user_id=1)

    assert review["empty"] is False
    for section in _REQUIRED_SECTIONS:
        assert section in review["content_md"]
    assert usage.estimated_cost_usd == 0.0  # no spend


# ---------------------------------------------------------------------------
# persistence: save / get / list + overwrite-confirm
# ---------------------------------------------------------------------------


def _review(week_start="2026-06-15", content="### What Worked\n\nv1") -> dict:
    return {
        "week_start": week_start,
        "empty": False,
        "content_md": content,
        "thinking_summary": "reasoning",
        "stats": {
            "trades": 2,
            "win_rate": 0.5,
            "total_pnl": 100.0,
            "profit_factor": 2.0,
            "total_edge_leak": -100.0,
        },
        "cost_usd": 0.012,
    }


def test_save_and_get_round_trip(in_memory_db):
    from src.tradelens.services.weekly import get_weekly_review, save_weekly_review

    save_weekly_review(_review(), user_id=1)
    got = get_weekly_review("2026-06-15", user_id=1)

    assert got is not None
    assert got["content_md"] == "### What Worked\n\nv1"
    assert got["stats"]["total_pnl"] == pytest.approx(100.0)
    assert got["cost_usd"] == pytest.approx(0.012)


def test_get_weekly_review_missing_returns_none(in_memory_db):
    from src.tradelens.services.weekly import get_weekly_review

    assert get_weekly_review("2099-01-04", user_id=1) is None


def test_overwrite_requires_confirm(in_memory_db):
    from src.tradelens.services.weekly import (
        WeeklyReviewExistsError,
        get_weekly_review,
        save_weekly_review,
    )

    save_weekly_review(_review(content="### What Worked\n\nv1"), user_id=1)

    # second save without overwrite must refuse
    with pytest.raises(WeeklyReviewExistsError):
        save_weekly_review(_review(content="### What Worked\n\nv2"), user_id=1)

    # overwrite=True replaces in place (still one row)
    save_weekly_review(
        _review(content="### What Worked\n\nv2"), overwrite=True, user_id=1
    )
    got = get_weekly_review("2026-06-15", user_id=1)
    assert got["content_md"] == "### What Worked\n\nv2"


# ---------------------------------------------------------------------------
# Strategy-context propagation + user scoping (MVP completion pass)
# ---------------------------------------------------------------------------


def test_generate_scopes_trades_to_user_and_includes_strategy():
    from src.tradelens.services.weekly import generate_weekly_review

    captured = {}

    def fake_get_trades(**kwargs):
        captured["kw"] = kwargs
        return _fake_trades()

    def fake_chat(user_message, system_message="", **kwargs):
        captured["user"] = user_message
        return _full_review(), _make_usage()

    with patch(
        "src.tradelens.services.weekly.get_trades", side_effect=fake_get_trades
    ), patch("src.tradelens.services.weekly.chat", side_effect=fake_chat), patch(
        "src.tradelens.services.weekly.load_prompt", return_value="mock"
    ):
        generate_weekly_review(
            "2026-06-17", user_id=7, strategy_profile={"name": "London FVG"}
        )

    assert captured["kw"]["user_id"] == 7
    assert "London FVG" in captured["user"]


def test_generate_without_profile_uses_general_framework_note():
    from src.tradelens.services.weekly import generate_weekly_review

    captured = {}

    def fake_chat(user_message, system_message="", **kwargs):
        captured["user"] = user_message
        return _full_review(), _make_usage()

    with patch(
        "src.tradelens.services.weekly.get_trades", return_value=_fake_trades()
    ), patch("src.tradelens.services.weekly.chat", side_effect=fake_chat), patch(
        "src.tradelens.services.weekly.load_prompt", return_value="mock"
    ):
        generate_weekly_review("2026-06-17", user_id=1)

    assert "No strategy profile provided" in captured["user"]


def test_dead_coach_generator_removed():
    """generate_ai_weekly_review had no UI path (evidence: only its own tests
    referenced it) and duplicated generate_weekly_review — it must stay gone."""
    import src.tradelens.services.weekly as weekly

    assert not hasattr(weekly, "generate_ai_weekly_review")
    assert not hasattr(weekly, "_AI_COACH_SYSTEM")


def test_prompt_asks_for_exactly_the_required_sections():
    """The prompt and the validator must agree on the section headings.

    They are two halves of one contract: the prompt tells the model what to
    write and _REQUIRED_SECTIONS rejects the result if it doesn't. A rename
    on one side silently fails every real generation.
    """
    from src.tradelens.services.weekly import _REQUIRED_SECTIONS

    prompt = (
        Path(__file__).resolve().parents[1] / "prompts" / "weekly_recap_v1.txt"
    ).read_text(encoding="utf-8")
    for heading in _REQUIRED_SECTIONS:
        assert heading in prompt, f"prompt is missing {heading!r}"


def test_no_signal_language_in_weekly_section_names():
    """TradeLens reviews completed trades; it does not emit signals."""
    from src.tradelens.services.weekly import _REQUIRED_SECTIONS

    assert not any("signal" in h.lower() for h in _REQUIRED_SECTIONS)
