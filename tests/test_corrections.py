"""
Tests for corrections.py — all DB operations use in-memory SQLite.
No network calls.
"""

import json
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import src.tradelens.services.metrics_store as metrics_store

from src.tradelens.db.models import (
    AIAnalysis,
    Base,
    Correction,
    PerformanceMetrics,
    Trade,
)


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
    monkeypatch.setattr("src.tradelens.services.corrections.SessionLocal", TestSession)
    return TestSession


@pytest.fixture()
def sample_ids(in_memory_db):
    """Create a Trade + AIAnalysis and return (trade_id, analysis_id)."""
    db = in_memory_db()
    trade = Trade(asset="NQ", direction="Long", result="Win")
    db.add(trade)
    db.flush()
    analysis = AIAnalysis(trade_id=trade.id, bias="bullish", trade_quality=7)
    db.add(analysis)
    db.commit()
    trade_id = trade.id
    analysis_id = analysis.id
    db.close()
    return trade_id, analysis_id


# ---------------------------------------------------------------------------
# _serialize helper (imported directly for unit testing)
# ---------------------------------------------------------------------------


def test_serialize_none_and_empty_string_are_equal():
    from src.tradelens.services.corrections import _serialize

    assert _serialize(None) == _serialize("")
    assert _serialize(None) is None


def test_serialize_list_is_stable_json():
    from src.tradelens.services.corrections import _serialize

    result = _serialize([{"b": 2, "a": 1}])
    parsed = json.loads(result)
    assert parsed == [{"b": 2, "a": 1}]
    assert '"a"' in result  # sort_keys → "a" before "b"
    assert result.index('"a"') < result.index('"b"')


def test_serialize_dict_sort_keys():
    from src.tradelens.services.corrections import _serialize

    r1 = _serialize({"z": 1, "a": 2})
    r2 = _serialize({"a": 2, "z": 1})
    assert r1 == r2  # stable regardless of insertion order


# ---------------------------------------------------------------------------
# record_correction
# ---------------------------------------------------------------------------


def test_record_writes_when_values_differ(in_memory_db, sample_ids):
    from src.tradelens.services.corrections import record_correction

    trade_id, analysis_id = sample_ids

    result = record_correction(trade_id, analysis_id, "bias", "bullish", "bearish")

    assert result is not None
    assert result.field == "bias"
    assert result.ai_value == "bullish"
    assert result.user_value == "bearish"
    assert result.created_at is not None  # always populated

    db = in_memory_db()
    rows = db.query(Correction).all()
    db.close()
    assert len(rows) == 1


def test_record_no_write_when_values_equal(in_memory_db, sample_ids):
    from src.tradelens.services.corrections import record_correction

    trade_id, analysis_id = sample_ids

    result = record_correction(trade_id, analysis_id, "bias", "bullish", "bullish")

    assert result is None

    db = in_memory_db()
    rows = db.query(Correction).all()
    db.close()
    assert len(rows) == 0


def test_record_none_vs_value_writes_row(in_memory_db, sample_ids):
    from src.tradelens.services.corrections import record_correction

    trade_id, analysis_id = sample_ids

    result = record_correction(
        trade_id, analysis_id, "detected_setup", None, "Order Block"
    )

    assert result is not None
    assert result.ai_value is None
    assert result.user_value == "Order Block"


def test_record_value_vs_none_writes_row(in_memory_db, sample_ids):
    from src.tradelens.services.corrections import record_correction

    trade_id, analysis_id = sample_ids

    result = record_correction(trade_id, analysis_id, "detected_setup", "FVG", None)

    assert result is not None
    assert result.ai_value == "FVG"
    assert result.user_value is None


def test_record_none_vs_none_no_write(in_memory_db, sample_ids):
    from src.tradelens.services.corrections import record_correction

    trade_id, analysis_id = sample_ids

    result = record_correction(trade_id, analysis_id, "detected_setup", None, None)

    assert result is None


def test_record_empty_string_vs_none_no_write(in_memory_db, sample_ids):
    """Empty string and None are treated as equivalent — no spurious row."""
    from src.tradelens.services.corrections import record_correction

    trade_id, analysis_id = sample_ids

    result = record_correction(trade_id, analysis_id, "detected_setup", "", None)

    assert result is None


def test_record_dict_serialized_as_stable_json(in_memory_db, sample_ids):
    from src.tradelens.services.corrections import record_correction

    trade_id, analysis_id = sample_ids

    ai_val = {"score": 7, "grade": "B"}
    user_val = {"score": 8, "grade": "A"}
    result = record_correction(trade_id, analysis_id, "grading", ai_val, user_val)

    assert result is not None
    stored_ai = json.loads(result.ai_value)
    assert stored_ai["score"] == 7


def test_record_equivalent_dicts_no_write(in_memory_db, sample_ids):
    """Two dicts with same content but different key order → no write."""
    from src.tradelens.services.corrections import record_correction

    trade_id, analysis_id = sample_ids

    result = record_correction(
        trade_id,
        analysis_id,
        "grading",
        {"b": 2, "a": 1},
        {"a": 1, "b": 2},
    )

    assert result is None


def test_record_grade_field(in_memory_db, sample_ids):
    from src.tradelens.services.corrections import record_correction

    trade_id, analysis_id = sample_ids

    result = record_correction(trade_id, analysis_id, "grade", "B", "A")

    assert result is not None
    assert result.field == "grade"
    assert result.ai_value == "B"
    assert result.user_value == "A"


# ---------------------------------------------------------------------------
# get_recent_corrections
# ---------------------------------------------------------------------------


def test_get_recent_corrections_returns_dicts(in_memory_db, sample_ids):
    from src.tradelens.services.corrections import (
        get_recent_corrections,
        record_correction,
    )

    trade_id, analysis_id = sample_ids

    record_correction(trade_id, analysis_id, "bias", "bullish", "bearish")
    record_correction(trade_id, analysis_id, "trade_quality", 5, 8)

    results = get_recent_corrections(limit=10)

    assert len(results) == 2
    assert isinstance(results[0], dict)
    assert results[0]["field"] == "trade_quality"  # most recent first (id DESC)
    assert results[1]["field"] == "bias"


def test_get_recent_corrections_respects_limit(in_memory_db, sample_ids):
    from src.tradelens.services.corrections import (
        get_recent_corrections,
        record_correction,
    )

    trade_id, analysis_id = sample_ids

    for i in range(5):
        record_correction(trade_id, analysis_id, "bias", "bullish", f"value_{i}")

    results = get_recent_corrections(limit=3)
    assert len(results) == 3


# ---------------------------------------------------------------------------
# metrics_store.get_computed_at
# ---------------------------------------------------------------------------


@pytest.fixture()
def pm_db(monkeypatch):
    """In-memory DB fixture patched onto metrics_store.SessionLocal."""
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(metrics_store, "SessionLocal", TestSession)
    return TestSession


def test_get_computed_at_returns_none_when_no_row(pm_db):
    from src.tradelens.services.metrics_store import get_computed_at

    assert get_computed_at(user_id=1) is None


def test_get_computed_at_returns_correct_timestamp(pm_db):
    from src.tradelens.services.metrics_store import get_computed_at

    db = pm_db()
    db.add(PerformanceMetrics(user_id=1, computed_at="2026-06-10T14:30:00+00:00"))
    db.commit()
    db.close()

    assert get_computed_at(user_id=1) == "2026-06-10T14:30:00+00:00"


# ---------------------------------------------------------------------------
# build_correction_few_shot (Week 5 Phase 5)
# ---------------------------------------------------------------------------


def test_build_few_shot_empty_returns_empty_string(monkeypatch):
    from src.tradelens.services import corrections

    monkeypatch.setattr(corrections, "get_recent_corrections", lambda **k: [])
    assert corrections.build_correction_few_shot() == ""


def test_build_few_shot_limit_zero_returns_empty(monkeypatch):
    from src.tradelens.services import corrections

    monkeypatch.setattr(
        corrections,
        "get_recent_corrections",
        lambda **k: [
            {"field": "bias", "user_value": "x", "ai_value": "y", "user_reason": None}
        ],
    )
    assert corrections.build_correction_few_shot(limit=0) == ""


def test_build_few_shot_orders_most_repeated_first(monkeypatch):
    from src.tradelens.services import corrections

    pool = [
        {
            "field": "setup_type",
            "user_value": "FVG",
            "ai_value": "OB",
            "user_reason": None,
        },  # most recent, but only once
        {
            "field": "bias",
            "user_value": "bearish",
            "ai_value": "bullish",
            "user_reason": None,
        },
        {
            "field": "bias",
            "user_value": "bearish",
            "ai_value": "bullish",
            "user_reason": None,
        },
        {
            "field": "bias",
            "user_value": "bearish",
            "ai_value": "bullish",
            "user_reason": None,
        },
    ]
    monkeypatch.setattr(corrections, "get_recent_corrections", lambda **k: pool)

    block = corrections.build_correction_few_shot()
    assert block.startswith("<past_corrections>")
    assert block.rstrip().endswith("</past_corrections>")
    # most-repeated (bias x3) ranks above the more-recent single setup_type correction
    assert block.index("bias") < block.index("setup_type")
    assert "3" in block  # repeat count surfaced


def test_build_few_shot_respects_token_budget(monkeypatch):
    from src.tradelens.services import corrections

    pool = [
        {
            "field": f"field_{i}",
            "user_value": "X" * 150,
            "ai_value": "Y" * 150,
            "user_reason": None,
        }
        for i in range(100)
    ]
    monkeypatch.setattr(corrections, "get_recent_corrections", lambda **k: pool)

    block = corrections.build_correction_few_shot(limit=100)
    assert corrections._estimate_tokens(block) <= 800
    assert block.count("\n- ") < 100  # truncated to fit the budget


# ---------------------------------------------------------------------------
# count_corrections / repeated_corrections (Week 5 Phase 5)
# ---------------------------------------------------------------------------


def test_count_corrections(in_memory_db, sample_ids):
    from src.tradelens.services.corrections import count_corrections, record_correction

    trade_id, analysis_id = sample_ids
    assert count_corrections() == 0
    record_correction(trade_id, analysis_id, "bias", "bullish", "bearish")
    record_correction(trade_id, analysis_id, "setup_type", "OB", "FVG")
    assert count_corrections() == 2


def test_repeated_corrections_fires_at_threshold(in_memory_db, sample_ids):
    from src.tradelens.services.corrections import (
        record_correction,
        repeated_corrections,
    )

    trade_id, analysis_id = sample_ids
    for _ in range(5):
        record_correction(trade_id, analysis_id, "bias", "bullish", "bearish")

    res = repeated_corrections(threshold=5)
    assert len(res) == 1
    assert res[0]["field"] == "bias"
    assert res[0]["user_value"] == "bearish"
    assert res[0]["count"] == 5


def test_repeated_corrections_below_threshold_excluded(in_memory_db, sample_ids):
    from src.tradelens.services.corrections import (
        record_correction,
        repeated_corrections,
    )

    trade_id, analysis_id = sample_ids
    for _ in range(4):
        record_correction(trade_id, analysis_id, "bias", "bullish", "bearish")

    assert repeated_corrections(threshold=5) == []
