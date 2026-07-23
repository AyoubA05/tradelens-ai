"""Legacy ownership assignment is dry-run first and never reassigns owned rows."""

import importlib
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

from src.tradelens.db.models import (
    AIAnalysis,
    Base,
    Correction,
    Strategy,
    Trade,
    User,
    WeeklyReview,
)


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "assign_legacy_data.py"


def test_assignment_script_exists():
    assert SCRIPT_PATH.exists(), "Legacy ownership assignment script is missing"


def test_assignment_script_imports_in_the_supported_test_environment():
    try:
        importlib.import_module("scripts.assign_legacy_data")
    except TypeError as exc:
        pytest.fail(str(exc))


def _assignment_module():
    assert SCRIPT_PATH.exists(), "Legacy ownership assignment script is missing"
    return importlib.import_module("scripts.assign_legacy_data")


@pytest.fixture
def assignment_db(monkeypatch):
    """Patch the assignment script onto a fresh SQLite database for every test."""
    assignment = _assignment_module()
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(assignment, "SessionLocal", session_factory)
    yield assignment, session_factory, engine
    Base.metadata.drop_all(engine)


def _seed_legacy_rows(session_factory):
    db = session_factory()
    owner = User(username="alice", password_hash="owner-hash")
    other = User(username="bob", password_hash="other-hash")
    db.add_all([owner, other])
    db.flush()

    legacy_trade = Trade(asset="NQ", user_id=None)
    other_trade = Trade(asset="ES", user_id=other.id)
    legacy_strategy = Strategy(name="Legacy profile", user_id=None)
    other_strategy = Strategy(name="Bob profile", user_id=other.id)
    legacy_review = WeeklyReview(week_start="2026-07-20", user_id=None)
    db.add_all(
        [
            legacy_trade,
            other_trade,
            legacy_strategy,
            other_strategy,
            legacy_review,
        ]
    )
    db.flush()

    analysis = AIAnalysis(trade_id=legacy_trade.id)
    db.add(analysis)
    db.flush()
    legacy_correction = Correction(
        trade_id=legacy_trade.id,
        ai_analysis_id=analysis.id,
        field="bias",
        user_id=None,
    )
    db.add(legacy_correction)
    db.commit()

    ids = {
        "owner": owner.id,
        "other": other.id,
        "legacy_trade": legacy_trade.id,
        "other_trade": other_trade.id,
        "legacy_strategy": legacy_strategy.id,
        "other_strategy": other_strategy.id,
        "legacy_review": legacy_review.id,
        "legacy_correction": legacy_correction.id,
    }
    db.close()
    return ids


def test_plan_reports_null_owned_rows_without_mutating_them(assignment_db):
    assignment, session_factory, _ = assignment_db
    ids = _seed_legacy_rows(session_factory)

    plan = assignment.plan_assignment("alice")

    assert plan.username == "alice"
    assert plan.user_id == ids["owner"]
    assert plan.counts == {
        "trades": 1,
        "strategies": 1,
        "weekly_reviews": 1,
        "corrections": 1,
    }

    db = session_factory()
    assert db.get(Trade, ids["legacy_trade"]).user_id is None
    assert db.get(Strategy, ids["legacy_strategy"]).user_id is None
    assert db.get(WeeklyReview, ids["legacy_review"]).user_id is None
    assert db.get(Correction, ids["legacy_correction"]).user_id is None
    db.close()


def test_apply_assigns_only_null_owned_rows_and_second_apply_changes_nothing(
    assignment_db,
):
    assignment, session_factory, _ = assignment_db
    ids = _seed_legacy_rows(session_factory)
    plan = assignment.plan_assignment("alice")

    assert assignment.apply_assignment(plan) == {
        "trades": 1,
        "strategies": 1,
        "weekly_reviews": 1,
        "corrections": 1,
    }
    assert assignment.apply_assignment(plan) == {
        "trades": 0,
        "strategies": 0,
        "weekly_reviews": 0,
        "corrections": 0,
    }

    db = session_factory()
    assert db.get(Trade, ids["legacy_trade"]).user_id == ids["owner"]
    assert db.get(Strategy, ids["legacy_strategy"]).user_id == ids["owner"]
    assert db.get(WeeklyReview, ids["legacy_review"]).user_id == ids["owner"]
    assert db.get(Correction, ids["legacy_correction"]).user_id == ids["owner"]
    assert db.get(Trade, ids["other_trade"]).user_id == ids["other"]
    assert db.get(Strategy, ids["other_strategy"]).user_id == ids["other"]
    db.close()


def test_unknown_username_is_exact_match_and_cli_exits_nonzero(assignment_db):
    assignment, session_factory, _ = assignment_db
    db = session_factory()
    db.add(User(username="Alice", password_hash="hash"))
    db.commit()
    db.close()

    with pytest.raises(ValueError, match="Unknown username: alice"):
        assignment.plan_assignment("alice")
    with pytest.raises(SystemExit) as exc_info:
        assignment.main(["--username", "alice"])

    assert exc_info.value.code != 0


def test_apply_rolls_back_every_table_when_an_update_fails(assignment_db):
    assignment, session_factory, engine = assignment_db
    ids = _seed_legacy_rows(session_factory)
    plan = assignment.plan_assignment("alice")

    def fail_strategy_update(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().startswith("UPDATE strategies"):
            raise RuntimeError("simulated strategy update failure")

    event.listen(engine, "before_cursor_execute", fail_strategy_update)
    try:
        with pytest.raises(RuntimeError, match="simulated strategy update failure"):
            assignment.apply_assignment(plan)
    finally:
        event.remove(engine, "before_cursor_execute", fail_strategy_update)

    db = session_factory()
    assert db.get(Trade, ids["legacy_trade"]).user_id is None
    assert db.get(Strategy, ids["legacy_strategy"]).user_id is None
    assert db.get(WeeklyReview, ids["legacy_review"]).user_id is None
    assert db.get(Correction, ids["legacy_correction"]).user_id is None
    db.close()
