"""
Tests for cost.py — monthly AI cost observability. In-memory SQLite, no network.
"""

from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.tradelens.db.models import (
    AIAnalysis,
    Base,
    Trade,
    User,
    WeeklyReview,
)

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture()
def in_memory_db(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr("src.tradelens.services.cost.SessionLocal", TestSession)
    return TestSession


def _add_analysis(db, user_id, cost, created_at):
    trade = Trade(asset="NQ", user_id=user_id)
    db.add(trade)
    db.flush()
    db.add(AIAnalysis(trade_id=trade.id, cost_usd=cost, created_at=created_at))


def test_monthly_cost_isolates_analysis_and_review_costs_by_user(in_memory_db):
    from src.tradelens.services.cost import monthly_cost_by_feature

    db = in_memory_db()
    alice = User(username="alice", password_hash="hash-a")
    bob = User(username="bob", password_hash="hash-b")
    db.add_all([alice, bob])
    db.flush()
    alice_id = alice.id
    bob_id = bob.id

    # two trade-analysis rows IN June, one OUT (May)
    _add_analysis(db, alice_id, 0.10, "2026-06-05T10:00:00+00:00")
    _add_analysis(db, alice_id, 0.20, "2026-06-20T10:00:00+00:00")
    _add_analysis(db, alice_id, 9.99, "2026-05-30T10:00:00+00:00")
    _add_analysis(db, bob_id, 8.00, "2026-06-21T10:00:00+00:00")
    # one weekly review IN June
    db.add_all(
        [
            WeeklyReview(
                user_id=alice_id,
                week_start="2026-06-15",
                cost_usd=0.05,
                created_at="2026-06-16T09:00:00+00:00",
            ),
            WeeklyReview(
                user_id=bob_id,
                week_start="2026-06-15",
                cost_usd=7.00,
                created_at="2026-06-16T09:00:00+00:00",
            ),
        ]
    )
    db.commit()
    db.close()

    df = monthly_cost_by_feature(2026, 6, user_id=alice_id)
    by_feature = dict(zip(df["feature"], df["cost_usd"]))
    calls = dict(zip(df["feature"], df["calls"]))

    assert by_feature["Trade Analysis (vision/journal/grading)"] == pytest.approx(0.30)
    assert by_feature["Weekly Review"] == pytest.approx(0.05)
    assert calls["Trade Analysis (vision/journal/grading)"] == 2
    assert calls["Weekly Review"] == 1
    # May row excluded
    assert all(v < 9.0 for v in df["cost_usd"])


def test_monthly_cost_counts_calls(in_memory_db):
    from src.tradelens.services.cost import monthly_cost_by_feature

    db = in_memory_db()
    alice = User(username="alice", password_hash="hash")
    db.add(alice)
    db.flush()
    alice_id = alice.id
    _add_analysis(db, alice_id, 0.10, "2026-06-05T10:00:00+00:00")
    _add_analysis(db, alice_id, 0.20, "2026-06-06T10:00:00+00:00")
    db.commit()
    db.close()

    df = monthly_cost_by_feature(2026, 6, user_id=alice_id)
    row = df[df["feature"] == "Trade Analysis (vision/journal/grading)"].iloc[0]
    assert int(row["calls"]) == 2


def test_monthly_cost_empty_month_returns_empty_frame(in_memory_db):
    from src.tradelens.services.cost import monthly_cost_by_feature

    df = monthly_cost_by_feature(2099, 1, user_id=1)
    assert df.empty
    assert list(df.columns) == ["feature", "cost_usd", "calls"]


@pytest.mark.parametrize("invalid_user_id", [None, 0, -1, True, "1"])
def test_monthly_cost_rejects_invalid_owner_before_opening_session(
    monkeypatch, invalid_user_id
):
    from src.tradelens.services import cost

    session_calls = 0

    def session_never_called():
        nonlocal session_calls
        session_calls += 1
        raise AssertionError("invalid owners must not construct a database session")

    monkeypatch.setattr(cost, "SessionLocal", session_never_called)

    with pytest.raises(ValueError, match="user_id must be a positive integer"):
        cost.monthly_cost_by_feature(2026, 7, user_id=invalid_user_id)

    assert session_calls == 0


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


def test_monthly_cost_isolates_usage_log_costs_and_calls_by_user(in_memory_db):
    from src.tradelens.services.cost import log_ai_usage, monthly_cost_by_feature

    log_ai_usage("AI Partner", _usage(cost=0.03), user_id=7)
    log_ai_usage("AI Partner", _usage(cost=0.01), user_id=7)
    log_ai_usage("Pattern Detection", _usage(cost=0.05), user_id=7)
    log_ai_usage("AI Partner", _usage(cost=8.00), user_id=8)
    log_ai_usage("AI Partner", _usage(cost=7.00), user_id=8)

    df = monthly_cost_by_feature(2026, 7, user_id=7)
    by_feature = dict(zip(df["feature"], df["cost_usd"]))
    assert by_feature["AI Partner"] == pytest.approx(0.04)
    assert by_feature["Pattern Detection"] == pytest.approx(0.05)
    calls = dict(zip(df["feature"], df["calls"]))
    assert calls["AI Partner"] == 2


def test_ownerless_settings_page_does_not_read_cost_data(monkeypatch):
    from streamlit.testing.v1 import AppTest

    from src.tradelens.services import cost

    service_calls = []

    def cost_service_called(*_args, **_kwargs):
        service_calls.append(True)
        raise AssertionError("ownerless page must not read AI cost data")

    monkeypatch.setattr(cost, "monthly_cost_by_feature", cost_service_called)

    at = AppTest.from_file(
        str(ROOT / "src" / "tradelens" / "ui" / "pages" / "9_Settings.py"),
        default_timeout=30,
    )
    at.session_state["authenticated"] = True
    at.run()

    assert not at.exception
    assert service_calls == []
