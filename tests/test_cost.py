"""
Tests for cost.py — monthly AI cost observability. In-memory SQLite, no network.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.tradelens.db.models import AIAnalysis, Base, WeeklyReview


@pytest.fixture()
def in_memory_db(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr("src.tradelens.services.cost.SessionLocal", TestSession)
    return TestSession


def test_monthly_cost_groups_by_feature_and_filters_month(in_memory_db):
    from src.tradelens.services.cost import monthly_cost_by_feature

    db = in_memory_db()
    # two trade-analysis rows IN June, one OUT (May)
    db.add(
        AIAnalysis(trade_id=1, cost_usd=0.10, created_at="2026-06-05T10:00:00+00:00")
    )
    db.add(
        AIAnalysis(trade_id=2, cost_usd=0.20, created_at="2026-06-20T10:00:00+00:00")
    )
    db.add(
        AIAnalysis(trade_id=3, cost_usd=9.99, created_at="2026-05-30T10:00:00+00:00")
    )
    # one weekly review IN June
    db.add(
        WeeklyReview(
            week_start="2026-06-15",
            cost_usd=0.05,
            created_at="2026-06-16T09:00:00+00:00",
        )
    )
    db.commit()
    db.close()

    df = monthly_cost_by_feature(2026, 6)
    by_feature = dict(zip(df["feature"], df["cost_usd"]))

    assert by_feature["Trade Analysis (vision/journal/grading)"] == pytest.approx(0.30)
    assert by_feature["Weekly Review"] == pytest.approx(0.05)
    # May row excluded
    assert all(v < 9.0 for v in df["cost_usd"])


def test_monthly_cost_counts_calls(in_memory_db):
    from src.tradelens.services.cost import monthly_cost_by_feature

    db = in_memory_db()
    db.add(
        AIAnalysis(trade_id=1, cost_usd=0.10, created_at="2026-06-05T10:00:00+00:00")
    )
    db.add(
        AIAnalysis(trade_id=2, cost_usd=0.20, created_at="2026-06-06T10:00:00+00:00")
    )
    db.commit()
    db.close()

    df = monthly_cost_by_feature(2026, 6)
    row = df[df["feature"] == "Trade Analysis (vision/journal/grading)"].iloc[0]
    assert int(row["calls"]) == 2


def test_monthly_cost_empty_month_returns_empty_frame(in_memory_db):
    from src.tradelens.services.cost import monthly_cost_by_feature

    df = monthly_cost_by_feature(2099, 1)
    assert df.empty
    assert list(df.columns) == ["feature", "cost_usd", "calls"]
