"""
Tests for grading.py — all AI calls mocked; no network.
DB persistence tests use in-memory SQLite.
"""

import json
from unittest.mock import patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.tradelens.db.models import AIAnalysis, Base, Trade
from src.tradelens.services.grading import (
    GradingError,
    _REQUIRED_RUBRIC_DIMS,
    build_grading_context,
    grade_trade,
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
    trade = Trade(
        asset="NQ",
        direction="Long",
        result="Win",
        pnl=500.0,
        emotions_during="Calm",
        notes="Followed rules perfectly.",
    )
    db.add(trade)
    db.flush()
    analysis = AIAnalysis(
        trade_id=trade.id,
        bias="bullish",
        detected_setup="OB",
        trade_quality=9,
        matched_strategy="ICT OB",
        mistakes_json=json.dumps([]),
        missed_opps_json=json.dumps([]),
    )
    db.add(analysis)
    db.commit()
    db.refresh(trade)
    db.refresh(analysis)
    db.close()
    return trade, analysis


def _make_usage() -> Usage:
    return Usage("claude-haiku-4-5", 300, 200, 500, 0.000165, 1.8)


def _make_grading(grade: str = "B", score: int = 7) -> dict:
    """Build a valid grading dict with all required fields."""
    return {
        "grade": grade,
        "score": score,
        "rubric": {
            dim: {"score": score, "note": f"Sample note for {dim}."}
            for dim in _REQUIRED_RUBRIC_DIMS
        },
        "one_line_verdict": f"Grade {grade}: solid process with room to improve.",
    }


# ---------------------------------------------------------------------------
# build_grading_context
# ---------------------------------------------------------------------------


def test_build_grading_context_extracts_fields(sample_analysis):
    trade, analysis = sample_analysis
    trade_dict, vision_dict = build_grading_context(trade, analysis)

    assert trade_dict["asset"] == "NQ"
    assert trade_dict["result"] == "Win"
    assert trade_dict["emotions_during"] == "Calm"
    assert vision_dict["bias"] == "bullish"
    assert vision_dict["detected_setup"] == "OB"
    assert isinstance(vision_dict["possible_mistakes"], list)


# ---------------------------------------------------------------------------
# grade_trade — mocked AI
# ---------------------------------------------------------------------------


def test_grade_trade_returns_dict_and_usage():
    trade = {"asset": "NQ", "direction": "Long", "result": "Win", "pnl": 300.0}
    vision = {
        "bias": "bullish",
        "detected_setup": "OB",
        "trade_quality": 9,
        "matched_strategy": None,
        "possible_mistakes": [],
        "missed_opportunities": [],
    }

    with patch(
        "src.tradelens.services.grading.chat",
        return_value=(json.dumps(_make_grading("A", 9)), _make_usage()),
    ), patch("src.tradelens.services.grading.load_prompt", return_value="mock prompt"):
        result, usage = grade_trade(trade, None, vision)

    assert result["grade"] == "A"
    assert result["score"] == 9
    assert set(result["rubric"].keys()) == _REQUIRED_RUBRIC_DIMS
    assert usage.model == "claude-haiku-4-5"


def test_grade_winning_reckless_trade():
    """Winning trade noted as undisciplined/reckless → mock returns low grade."""
    trade = {
        "asset": "NQ",
        "result": "Win",
        "pnl": 800.0,
        "notes": "Ignored stop, got lucky.",
    }
    vision = {
        "bias": "bullish",
        "detected_setup": None,
        "trade_quality": 2,
        "matched_strategy": None,
        "possible_mistakes": ["No stop loss", "Over-sized position"],
        "missed_opportunities": [],
    }

    grading = _make_grading("F", 2)
    with patch(
        "src.tradelens.services.grading.chat",
        return_value=(json.dumps(grading), _make_usage()),
    ), patch("src.tradelens.services.grading.load_prompt", return_value="mock"):
        result, _ = grade_trade(trade, None, vision)

    assert result["grade"] in ("D", "F")
    assert result["score"] <= 4


def test_grade_losing_disciplined_trade():
    """Losing trade with perfect process → mock returns high grade."""
    trade = {
        "asset": "EURUSD",
        "result": "Loss",
        "pnl": -50.0,
        "notes": "Stopped out cleanly. Setup was valid but invalidated.",
    }
    vision = {
        "bias": "bearish",
        "detected_setup": "FVG",
        "trade_quality": 8,
        "matched_strategy": "ICT",
        "possible_mistakes": [],
        "missed_opportunities": [],
    }

    grading = _make_grading("A", 9)
    with patch(
        "src.tradelens.services.grading.chat",
        return_value=(json.dumps(grading), _make_usage()),
    ), patch("src.tradelens.services.grading.load_prompt", return_value="mock"):
        result, _ = grade_trade(trade, None, vision)

    assert result["grade"] in ("A", "B")
    assert result["score"] >= 7


def test_grade_no_strategy_uses_fallback():
    """With strategy_profile=None, fallback text must appear in user message."""
    trade = {"asset": "NQ"}
    vision = {
        "bias": "bullish",
        "detected_setup": None,
        "trade_quality": 5,
        "matched_strategy": None,
        "possible_mistakes": [],
        "missed_opportunities": [],
    }

    captured = {}

    def fake_chat(user_message, system_message="", model=None, response_format=None):
        captured["user"] = user_message
        return json.dumps(_make_grading()), _make_usage()

    with patch("src.tradelens.services.grading.chat", side_effect=fake_chat), patch(
        "src.tradelens.services.grading.load_prompt", return_value="mock"
    ):
        grade_trade(trade, None, vision)

    assert "No strategy profile provided" in captured["user"]


def test_grade_missing_top_level_key_raises():
    """JSON missing 'grade' key → GradingError."""
    bad = {"score": 5, "rubric": {}, "one_line_verdict": "ok"}

    with patch(
        "src.tradelens.services.grading.chat",
        return_value=(json.dumps(bad), _make_usage()),
    ), patch("src.tradelens.services.grading.load_prompt", return_value="mock"):
        with pytest.raises(GradingError, match="missing top-level keys"):
            grade_trade({}, None, {})


def test_grade_missing_rubric_dimension_raises():
    """rubric missing 'emotional_control' → GradingError."""
    dims_minus_one = _REQUIRED_RUBRIC_DIMS - {"emotional_control"}
    bad_rubric = {dim: {"score": 5, "note": "ok"} for dim in dims_minus_one}
    bad = {"grade": "B", "score": 7, "rubric": bad_rubric, "one_line_verdict": "ok"}

    with patch(
        "src.tradelens.services.grading.chat",
        return_value=(json.dumps(bad), _make_usage()),
    ), patch("src.tradelens.services.grading.load_prompt", return_value="mock"):
        with pytest.raises(GradingError, match="emotional_control"):
            grade_trade({}, None, {})


def test_grade_rubric_missing_note_raises():
    """rubric dimension missing 'note' field → GradingError."""
    rubric = {dim: {"score": 5, "note": "ok"} for dim in _REQUIRED_RUBRIC_DIMS}
    rubric["entry_quality"] = {"score": 5}  # missing 'note'
    bad = {"grade": "C", "score": 5, "rubric": rubric, "one_line_verdict": "ok"}

    with patch(
        "src.tradelens.services.grading.chat",
        return_value=(json.dumps(bad), _make_usage()),
    ), patch("src.tradelens.services.grading.load_prompt", return_value="mock"):
        with pytest.raises(GradingError, match="entry_quality"):
            grade_trade({}, None, {})


def test_grade_trade_ai_unavailable_raises():
    """A refusal/outage (AIUnavailable) is surfaced as a typed GradingError."""
    from src.tradelens.services.ai_client import AIUnavailable

    with patch(
        "src.tradelens.services.grading.chat",
        return_value=(AIUnavailable("AI declined"), _make_usage()),
    ), patch("src.tradelens.services.grading.load_prompt", return_value="mock"):
        with pytest.raises(GradingError, match="AI declined"):
            grade_trade({}, None, {})


def test_grade_missing_prompt_raises():
    with patch(
        "src.tradelens.services.grading.load_prompt",
        side_effect=FileNotFoundError("missing"),
    ):
        with pytest.raises(FileNotFoundError):
            grade_trade({}, None, {})


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------


def test_save_grade_writes_grading_json_and_ai_grade(sample_analysis, in_memory_db):
    from src.tradelens.services.ai_analysis_service import save_grade

    trade, analysis = sample_analysis
    grading = _make_grading("A", 9)

    save_grade(analysis.id, grading)

    db = in_memory_db()
    row = db.query(AIAnalysis).filter(AIAnalysis.id == analysis.id).first()
    t = db.query(Trade).filter(Trade.id == trade.id).first()
    db.close()

    assert row.grading_json is not None
    assert json.loads(row.grading_json)["grade"] == "A"
    assert t.ai_grade == "A"


def test_save_user_grade_does_not_overwrite_ai_grade(sample_analysis, in_memory_db):
    from src.tradelens.services.ai_analysis_service import save_grade, save_user_grade

    trade, analysis = sample_analysis
    save_grade(analysis.id, _make_grading("B", 7))
    save_user_grade(trade.id, "A")

    db = in_memory_db()
    t = db.query(Trade).filter(Trade.id == trade.id).first()
    db.close()

    assert t.ai_grade == "B"
    assert t.user_grade == "A"


def test_save_user_grade_can_clear_to_null(sample_analysis, in_memory_db):
    from src.tradelens.services.ai_analysis_service import save_user_grade

    trade, _ = sample_analysis
    save_user_grade(trade.id, "C")
    save_user_grade(trade.id, None)  # clear

    db = in_memory_db()
    t = db.query(Trade).filter(Trade.id == trade.id).first()
    db.close()

    assert t.user_grade is None
