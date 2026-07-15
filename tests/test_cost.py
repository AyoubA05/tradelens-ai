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


# ---------------------------------------------------------------------------
# log_ai_usage + AIUsageLog — per-call usage rows for features that have no
# natural persistence row (AI Partner, Pattern Detection), so the Settings
# cost dashboard reflects real spend.
# ---------------------------------------------------------------------------


def _usage(cost=0.01, tokens_in=100, tokens_out=50, model="claude-fable-5"):
    from src.tradelens.services.ai_client import Usage

    return Usage(
        model=model,
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        total_tokens=tokens_in + tokens_out,
        estimated_cost_usd=cost,
        latency_s=0.5,
    )


def test_log_ai_usage_writes_row(in_memory_db):
    from src.tradelens.db.models import AIUsageLog
    from src.tradelens.services.cost import log_ai_usage

    log_ai_usage("AI Partner", _usage(cost=0.02), user_id=7)

    db = in_memory_db()
    rows = db.query(AIUsageLog).all()
    db.close()
    assert len(rows) == 1
    assert rows[0].feature == "AI Partner"
    assert rows[0].cost_usd == 0.02
    assert rows[0].tokens_input == 100
    assert rows[0].tokens_output == 50
    assert rows[0].user_id == 7
    assert rows[0].created_at  # stamped


def test_log_ai_usage_never_raises(in_memory_db, monkeypatch):
    from src.tradelens.services import cost as cost_mod

    def boom():
        raise RuntimeError("db down")

    monkeypatch.setattr(cost_mod, "SessionLocal", boom)
    cost_mod.log_ai_usage("AI Partner", _usage())  # must not raise


def test_log_ai_usage_ignores_none_usage(in_memory_db):
    from src.tradelens.db.models import AIUsageLog
    from src.tradelens.services.cost import log_ai_usage

    log_ai_usage("AI Partner", None)
    db = in_memory_db()
    assert db.query(AIUsageLog).count() == 0
    db.close()


def test_monthly_cost_includes_usage_log_features(in_memory_db):
    from src.tradelens.services.cost import log_ai_usage, monthly_cost_by_feature

    log_ai_usage("AI Partner", _usage(cost=0.03))
    log_ai_usage("AI Partner", _usage(cost=0.01))
    log_ai_usage("Pattern Detection", _usage(cost=0.05))

    df = monthly_cost_by_feature(2026, 7)
    by_feature = dict(zip(df["feature"], df["cost_usd"]))
    assert by_feature["AI Partner"] == pytest.approx(0.04)
    assert by_feature["Pattern Detection"] == pytest.approx(0.05)
    calls = dict(zip(df["feature"], df["calls"]))
    assert calls["AI Partner"] == 2
