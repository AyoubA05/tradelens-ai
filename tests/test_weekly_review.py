"""
AI Weekly Coach (Session D2): user-scoped persistence + post-trade-only prompt.
"""

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

import src.tradelens.services.ai_client as ai_client
import src.tradelens.services.weekly as weekly
from src.tradelens.db.models import Base
from src.tradelens.services.weekly import _AI_COACH_SYSTEM


@pytest.fixture
def in_memory_db(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    InMemorySession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(weekly, "SessionLocal", InMemorySession)
    yield InMemorySession
    Base.metadata.drop_all(engine)


def test_weekly_reviews_table_created():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    cols = {c["name"] for c in inspect(engine).get_columns("weekly_reviews")}
    assert "user_id" in cols
    assert "week_start" in cols


def test_save_and_retrieve_weekly_review(in_memory_db):
    review = {
        "week_start": "2026-06-22",
        "content_md": "Strong, disciplined week.",
        "stats": {"trades": 5, "total_pnl": 500.0},
    }
    weekly.save_weekly_review(review, user_id=1)
    rows = weekly.get_weekly_reviews(user_id=1)
    assert len(rows) == 1
    assert rows[0]["content_md"] == "Strong, disciplined week."
    assert rows[0]["week_start"] == "2026-06-22"


def test_weekly_review_user_scoping(in_memory_db):
    # Same week, two users — each only sees their own review.
    weekly.save_weekly_review(
        {"week_start": "2026-06-22", "content_md": "User A", "stats": {}}, user_id=1
    )
    weekly.save_weekly_review(
        {"week_start": "2026-06-22", "content_md": "User B", "stats": {}}, user_id=2
    )
    a = weekly.get_weekly_reviews(user_id=1)
    b = weekly.get_weekly_reviews(user_id=2)
    assert [r["content_md"] for r in a] == ["User A"]
    assert [r["content_md"] for r in b] == ["User B"]


def test_weekly_ai_system_prompt():
    prompt = _AI_COACH_SYSTEM.lower()
    assert "signal" in prompt
    assert "predict" in prompt or "prediction" in prompt
    assert "never" in prompt


def test_weekly_review_small_sample(monkeypatch):
    monkeypatch.setattr(ai_client.settings, "demo_mode", True)
    text = weekly.generate_ai_weekly_review({"trades": 2, "total_pnl": 100.0})
    assert isinstance(text, str) and text.strip()
