"""
Tests for Day 3 AI analysis persistence layer.
All DB operations use in-memory SQLite; no network calls.
"""
import json

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.tradelens.db.models import AIAnalysis, Base, Trade
from src.tradelens.services.ai_client import Usage


# ---------------------------------------------------------------------------
# In-memory DB fixture — mirrors pattern from test_trade_service.py
# ---------------------------------------------------------------------------

@pytest.fixture()
def in_memory_db(monkeypatch):
    """
    Spin up a fresh in-memory SQLite engine and patch SessionLocal
    so service functions use it instead of the file-backed DB.
    """
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)

    monkeypatch.setattr("src.tradelens.services.ai_analysis_service.SessionLocal", TestSession)
    return TestSession


@pytest.fixture()
def sample_trade(in_memory_db):
    """Insert a minimal Trade row and return it."""
    db = in_memory_db()
    trade = Trade(asset="NQ", direction="Long", result="Win", pnl=250.0)
    db.add(trade)
    db.commit()
    db.refresh(trade)
    db.close()
    return trade


def _make_usage(model: str = "claude-fable-5") -> Usage:
    return Usage(
        model=model,
        tokens_in=300,
        tokens_out=150,
        total_tokens=450,
        estimated_cost_usd=0.00375,
        latency_s=1.5,
    )


_VISION_RESULT = {
    "bias": "bullish",
    "bias_confidence": 0.8,
    "detected_timeframe": "15m",
    "detected_asset": "NQ",
    "structure": "Higher highs, bullish trend.",
    "bos": True,
    "choch": False,
    "key_zones": [
        {
            "type": "order_block",
            "description": "Bearish OB acting as support",
            "approx_price": 19250.0,
            "confidence": 0.75,
        }
    ],
    "matched_strategy": "ICT OB Retest",
    "matched_strategy_reason": "Entry at OB after BOS confirmation.",
    "possible_mistakes": ["Entry slightly late"],
    "missed_opportunities": ["Could have scaled at OB"],
    "trade_quality": 7,
    "notes_to_user": "Solid read. Tighten entry timing next time.",
}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_create_analysis_persists_all_fields(sample_trade, in_memory_db):
    from src.tradelens.services.ai_analysis_service import create_or_update_analysis

    usage = _make_usage()
    row = create_or_update_analysis(sample_trade.id, _VISION_RESULT, usage)

    assert row.id is not None
    assert row.trade_id == sample_trade.id
    assert row.model == "claude-fable-5"
    assert row.prompt_version == "screenshot_v1"
    assert row.bias == "bullish"
    assert row.detected_setup is None  # not set by Day 2 vision
    assert row.trade_quality == 7
    assert row.tokens_input == 300
    assert row.tokens_output == 150
    assert abs(row.cost_usd - 0.00375) < 1e-6
    assert row.matched_strategy == "ICT OB Retest"
    assert row.created_at is not None
    assert row.updated_at is not None


def test_get_analysis_returns_existing_row(sample_trade, in_memory_db):
    from src.tradelens.services.ai_analysis_service import (
        create_or_update_analysis,
        get_analysis_for_trade,
    )

    create_or_update_analysis(sample_trade.id, _VISION_RESULT, _make_usage())
    result = get_analysis_for_trade(sample_trade.id)

    assert result is not None
    assert result.trade_id == sample_trade.id
    assert result.bias == "bullish"


def test_get_analysis_returns_none_for_unknown_trade(in_memory_db):
    from src.tradelens.services.ai_analysis_service import get_analysis_for_trade

    assert get_analysis_for_trade(99999) is None


def test_create_or_update_overwrites_on_rerun(sample_trade, in_memory_db):
    from src.tradelens.services.ai_analysis_service import (
        create_or_update_analysis,
    )

    create_or_update_analysis(sample_trade.id, _VISION_RESULT, _make_usage())

    updated_result = {**_VISION_RESULT, "bias": "bearish", "trade_quality": 4}
    create_or_update_analysis(sample_trade.id, updated_result, _make_usage())

    db = in_memory_db()
    rows = db.query(AIAnalysis).filter(AIAnalysis.trade_id == sample_trade.id).all()
    db.close()

    assert len(rows) == 1  # still one row, not two
    assert rows[0].bias == "bearish"
    assert rows[0].trade_quality == 4


def test_zones_json_roundtrip(sample_trade, in_memory_db):
    from src.tradelens.services.ai_analysis_service import create_or_update_analysis

    row = create_or_update_analysis(sample_trade.id, _VISION_RESULT, _make_usage())

    zones = json.loads(row.zones_json)
    assert isinstance(zones, list)
    assert len(zones) == 1
    assert zones[0]["type"] == "order_block"
    assert zones[0]["approx_price"] == 19250.0
    assert zones[0]["confidence"] == 0.75


def test_raw_response_json_roundtrip(sample_trade, in_memory_db):
    from src.tradelens.services.ai_analysis_service import create_or_update_analysis

    row = create_or_update_analysis(sample_trade.id, _VISION_RESULT, _make_usage())

    raw = json.loads(row.raw_response_json)
    assert raw["bias"] == "bullish"
    assert raw["trade_quality"] == 7
    assert len(raw["key_zones"]) == 1


def test_save_journal_persists_markdown(sample_trade, in_memory_db):
    from src.tradelens.services.ai_analysis_service import (
        create_or_update_analysis,
        save_journal,
        get_analysis_for_trade,
    )

    row = create_or_update_analysis(sample_trade.id, _VISION_RESULT, _make_usage())
    markdown = "### Trade Summary\nSolid trade.\n### Market Bias\nBullish."
    updated = save_journal(row.id, markdown)

    assert updated.journal_entry_md == markdown
    assert updated.updated_at is not None

    reloaded = get_analysis_for_trade(sample_trade.id)
    assert reloaded.journal_entry_md == markdown


def test_save_grade_writes_grading_json_and_ai_grade(sample_trade, in_memory_db):
    from src.tradelens.services.ai_analysis_service import (
        create_or_update_analysis,
        save_grade,
    )

    row = create_or_update_analysis(sample_trade.id, _VISION_RESULT, _make_usage())
    grading_result = {
        "grade": "B",
        "score": 7,
        "one_line_verdict": "Disciplined entry, early exit.",
        "rubric": {
            "entry_quality": {"score": 8, "note": "Clean OB retest."},
            "risk_management": {"score": 7, "note": "Stop was correct."},
            "exit_quality": {"score": 5, "note": "Exited before TP."},
            "rule_adherence": {"score": 8, "note": "Followed all rules."},
            "emotional_control": {"score": 7, "note": "No revenge trading."},
        },
    }
    updated = save_grade(row.id, grading_result)

    assert updated.grading_json is not None
    saved = json.loads(updated.grading_json)
    assert saved["grade"] == "B"
    assert saved["score"] == 7

    # Verify ai_grade was denormalized to trades table
    db = in_memory_db()
    trade = db.query(Trade).filter(Trade.id == sample_trade.id).first()
    db.close()
    assert trade.ai_grade == "B"


def test_save_user_grade_does_not_overwrite_ai_grade(sample_trade, in_memory_db):
    from src.tradelens.services.ai_analysis_service import (
        create_or_update_analysis,
        save_grade,
        save_user_grade,
    )

    row = create_or_update_analysis(sample_trade.id, _VISION_RESULT, _make_usage())
    grading_result = {
        "grade": "C", "score": 5, "one_line_verdict": "Mediocre.",
        "rubric": {
            "entry_quality": {"score": 5, "note": "Late entry."},
            "risk_management": {"score": 5, "note": "OK."},
            "exit_quality": {"score": 5, "note": "OK."},
            "rule_adherence": {"score": 5, "note": "Mostly."},
            "emotional_control": {"score": 5, "note": "OK."},
        },
    }
    save_grade(row.id, grading_result)
    save_user_grade(sample_trade.id, "A")

    db = in_memory_db()
    trade = db.query(Trade).filter(Trade.id == sample_trade.id).first()
    db.close()

    assert trade.ai_grade == "C"   # AI grade unchanged
    assert trade.user_grade == "A"  # user override set


def test_save_user_grade_can_clear_to_null(sample_trade, in_memory_db):
    from src.tradelens.services.ai_analysis_service import save_user_grade

    save_user_grade(sample_trade.id, "B")
    save_user_grade(sample_trade.id, None)

    db = in_memory_db()
    trade = db.query(Trade).filter(Trade.id == sample_trade.id).first()
    db.close()
    assert trade.user_grade is None


def test_update_analysis_fields_denormalizes_to_trade(sample_trade, in_memory_db):
    from src.tradelens.services.ai_analysis_service import (
        create_or_update_analysis,
        update_analysis_fields,
    )

    row = create_or_update_analysis(sample_trade.id, _VISION_RESULT, _make_usage())
    update_analysis_fields(row.id, bias="bearish", detected_setup="FVG", trade_quality=6)

    # Check that trade row was also updated
    db = in_memory_db()
    trade = db.query(Trade).filter(Trade.id == sample_trade.id).first()
    db.close()

    assert trade.bias == "bearish"
    assert trade.setup_type == "FVG"

    # Check analysis row was updated
    db2 = in_memory_db()
    analysis = db2.query(AIAnalysis).filter(AIAnalysis.id == row.id).first()
    db2.close()

    assert analysis.bias == "bearish"
    assert analysis.detected_setup == "FVG"
    assert analysis.trade_quality == 6
