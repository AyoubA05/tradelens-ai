"""
Tests for journal.py — all AI calls are mocked; no network traffic, no cost.
DB tests use in-memory SQLite.
"""

import json
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.tradelens.db.models import AIAnalysis, Base, Trade
from src.tradelens.services.journal import (
    JournalStructureError,
    _REQUIRED_SECTIONS,
    build_journal_context,
    generate_journal,
)
from src.tradelens.services.ai_client import Usage


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def in_memory_db(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(
        "src.tradelens.services.ai_analysis_service.SessionLocal", TestSession
    )
    return TestSession


@pytest.fixture()
def sample_analysis(in_memory_db):
    db = in_memory_db()
    trade = Trade(user_id=1, asset="NQ", direction="Long", result="Win", pnl=300.0)
    db.add(trade)
    db.flush()
    analysis = AIAnalysis(
        trade_id=trade.id,
        bias="bullish",
        detected_setup="FVG",
        trade_quality=8,
        matched_strategy="ICT OB Retest",
        zones_json=json.dumps(
            [
                {
                    "type": "order_block",
                    "description": "Bearish OB",
                    "approx_price": 19200.0,
                    "confidence": 0.8,
                }
            ]
        ),
        mistakes_json=json.dumps(["Entry slightly late"]),
        missed_opps_json=json.dumps(["Could have scaled at OB"]),
    )
    db.add(analysis)
    db.commit()
    db.refresh(trade)
    db.refresh(analysis)
    db.close()
    return trade, analysis


def _full_journal() -> str:
    """Return a mock journal with all 8 required sections in order."""
    return "\n\n".join(
        f"{h}\n\nSample content for {h.lstrip('#').strip()}."
        for h in _REQUIRED_SECTIONS
    )


def _make_usage() -> Usage:
    return Usage(
        model="claude-fable-5",
        tokens_in=400,
        tokens_out=600,
        total_tokens=1000,
        estimated_cost_usd=0.000420,
        latency_s=2.1,
    )


# ---------------------------------------------------------------------------
# build_journal_context
# ---------------------------------------------------------------------------


def test_build_journal_context_extracts_trade_and_analysis_fields(sample_analysis):
    trade, analysis = sample_analysis
    trade_dict, ai_dict = build_journal_context(trade, analysis)

    assert trade_dict["asset"] == "NQ"
    assert trade_dict["direction"] == "Long"
    assert trade_dict["result"] == "Win"

    assert ai_dict["bias"] == "bullish"
    assert ai_dict["detected_setup"] == "FVG"
    assert ai_dict["trade_quality"] == 8
    assert isinstance(ai_dict["key_zones"], list)
    assert ai_dict["key_zones"][0]["type"] == "order_block"
    assert isinstance(ai_dict["possible_mistakes"], list)
    assert ai_dict["possible_mistakes"][0] == "Entry slightly late"


# ---------------------------------------------------------------------------
# generate_journal
# ---------------------------------------------------------------------------


def test_generate_journal_returns_markdown_and_usage():
    trade = {"asset": "NQ", "direction": "Long", "result": "Win", "pnl": 300.0}
    ai_analysis = {
        "bias": "bullish",
        "detected_setup": "FVG",
        "trade_quality": 8,
        "matched_strategy": None,
        "key_zones": [],
        "possible_mistakes": [],
        "missed_opportunities": [],
    }

    with patch(
        "src.tradelens.services.journal.chat",
        return_value=(_full_journal(), _make_usage()),
    ), patch(
        "src.tradelens.services.journal.load_prompt", return_value="mock system prompt"
    ):
        result, usage = generate_journal(trade, ai_analysis)

    assert isinstance(result, str)
    assert "### Trade Summary" in result
    assert usage.model == "claude-fable-5"


def test_generate_journal_contains_all_eight_sections():
    trade = {"asset": "EURUSD", "direction": "Short", "result": "Loss", "pnl": -120.0}
    ai_analysis = {
        "bias": "bearish",
        "detected_setup": None,
        "trade_quality": 5,
        "matched_strategy": None,
        "key_zones": [],
        "possible_mistakes": [],
        "missed_opportunities": [],
    }

    with patch(
        "src.tradelens.services.journal.chat",
        return_value=(_full_journal(), _make_usage()),
    ), patch("src.tradelens.services.journal.load_prompt", return_value="mock"):
        result, _ = generate_journal(trade, ai_analysis)

    for section in _REQUIRED_SECTIONS:
        assert section in result, f"Missing section: {section}"


def test_generate_journal_strategy_aware():
    """Strategy profile content must reach the chat() user_message."""
    trade = {"asset": "NQ", "direction": "Long", "result": "Win", "pnl": 250.0}
    ai_analysis = {
        "bias": "bullish",
        "detected_setup": "OB",
        "trade_quality": 9,
        "matched_strategy": "ICT",
        "key_zones": [],
        "possible_mistakes": [],
        "missed_opportunities": [],
    }
    strategy = {"name": "ICT Precision", "entry_rules": "BOS + OB retest only"}

    captured_messages = {}

    def fake_chat(
        user_message, system_message="", model=None, response_format=None, **kwargs
    ):
        captured_messages["user"] = user_message
        return _full_journal(), _make_usage()

    with patch("src.tradelens.services.journal.chat", side_effect=fake_chat), patch(
        "src.tradelens.services.journal.load_prompt", return_value="mock"
    ):
        generate_journal(trade, ai_analysis, strategy_profile=strategy)

    assert "ICT Precision" in captured_messages["user"]
    assert "BOS + OB retest only" in captured_messages["user"]


def test_generate_journal_no_strategy_fallback():
    """With strategy_profile=None the generic fallback text should be in the user message."""
    trade = {"asset": "NQ", "direction": "Long", "result": "Win", "pnl": 200.0}
    ai_analysis = {
        "bias": "bullish",
        "detected_setup": None,
        "trade_quality": 7,
        "matched_strategy": None,
        "key_zones": [],
        "possible_mistakes": [],
        "missed_opportunities": [],
    }

    captured_messages = {}

    def fake_chat(
        user_message, system_message="", model=None, response_format=None, **kwargs
    ):
        captured_messages["user"] = user_message
        return _full_journal(), _make_usage()

    with patch("src.tradelens.services.journal.chat", side_effect=fake_chat), patch(
        "src.tradelens.services.journal.load_prompt", return_value="mock"
    ):
        generate_journal(trade, ai_analysis, strategy_profile=None)

    assert "No strategy profile provided" in captured_messages["user"]


def test_generate_journal_ai_unavailable_raises():
    """A refusal/outage (AIUnavailable) is surfaced as a typed JournalStructureError."""
    from src.tradelens.services.ai_client import AIUnavailable

    with patch(
        "src.tradelens.services.journal.chat",
        return_value=(AIUnavailable("AI declined"), _make_usage()),
    ), patch("src.tradelens.services.journal.load_prompt", return_value="mock"):
        with pytest.raises(JournalStructureError, match="AI declined"):
            generate_journal({"asset": "NQ"}, {})


def test_generate_journal_missing_prompt_raises():
    trade = {"asset": "NQ"}
    ai_analysis = {}

    with patch(
        "src.tradelens.services.journal.load_prompt",
        side_effect=FileNotFoundError("missing"),
    ):
        with pytest.raises(FileNotFoundError, match="missing"):
            generate_journal(trade, ai_analysis)


def test_generate_journal_missing_section_raises():
    """Journal with a missing H3 section must raise JournalStructureError."""
    incomplete = "### Trade Summary\n\nOK\n\n### Market Bias\n\nOK"  # only 2 of 8

    trade = {"asset": "NQ"}
    ai_analysis = {}

    with patch(
        "src.tradelens.services.journal.chat", return_value=(incomplete, _make_usage())
    ), patch("src.tradelens.services.journal.load_prompt", return_value="mock"):
        with pytest.raises(JournalStructureError, match="missing required section"):
            generate_journal(trade, ai_analysis)


def test_generate_journal_out_of_order_sections_raises():
    """Sections present but in wrong order must raise JournalStructureError."""
    # Swap Market Bias and Trade Summary
    sections = list(_REQUIRED_SECTIONS)
    sections[0], sections[1] = sections[1], sections[0]
    out_of_order = "\n\n".join(f"{h}\n\nContent." for h in sections)

    trade = {"asset": "NQ"}
    ai_analysis = {}

    with patch(
        "src.tradelens.services.journal.chat",
        return_value=(out_of_order, _make_usage()),
    ), patch("src.tradelens.services.journal.load_prompt", return_value="mock"):
        with pytest.raises(JournalStructureError, match="out of order"):
            generate_journal(trade, ai_analysis)


# ---------------------------------------------------------------------------
# save_journal persistence
# ---------------------------------------------------------------------------


def test_save_journal_persists_markdown(sample_analysis, in_memory_db):
    from src.tradelens.services.ai_analysis_service import save_journal

    _, analysis = sample_analysis
    md = _full_journal()

    save_journal(analysis.id, md, user_id=1)

    db = in_memory_db()
    row = db.query(AIAnalysis).filter(AIAnalysis.id == analysis.id).first()
    db.close()

    assert row.journal_entry_md == md
    assert row.updated_at is not None
