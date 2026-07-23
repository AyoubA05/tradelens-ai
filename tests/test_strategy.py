"""
Tests for strategy.py — all DB operations use in-memory SQLite.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.tradelens.db.models import Base, Strategy, User


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
def in_memory_db(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr("src.tradelens.services.strategy.SessionLocal", TestSession)
    return TestSession


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_strategy_profiles_are_isolated_between_users(in_memory_db):
    from src.tradelens.services.strategy import (
        get_active_strategy,
        upsert_strategy_profile,
    )

    db = in_memory_db()
    alice = User(username="alice", password_hash="hash")
    bob = User(username="bob", password_hash="hash")
    db.add_all([alice, bob])
    db.commit()
    db.refresh(alice)
    db.refresh(bob)
    db.close()

    upsert_strategy_profile(alice.id, name="Alice Strategy")
    upsert_strategy_profile(bob.id, name="Bob Strategy")

    assert get_active_strategy(alice.id)["name"] == "Alice Strategy"
    assert get_active_strategy(bob.id)["name"] == "Bob Strategy"

    upsert_strategy_profile(bob.id, name="Bob Updated Strategy")

    assert get_active_strategy(alice.id)["name"] == "Alice Strategy"
    assert get_active_strategy(bob.id)["name"] == "Bob Updated Strategy"


def test_strategy_operations_reject_none_without_touching_legacy_profile(in_memory_db):
    from src.tradelens.services.strategy import (
        append_insight,
        get_active_strategy,
        upsert_strategy_profile,
    )

    db = in_memory_db()
    db.add(
        Strategy(
            name="Legacy Profile",
            user_id=None,
            is_active=1,
            risk_rules="Legacy risk rule",
        )
    )
    db.commit()
    db.close()

    with pytest.raises(ValueError, match="user_id must be a positive integer"):
        get_active_strategy(None)
    with pytest.raises(ValueError, match="user_id must be a positive integer"):
        upsert_strategy_profile(None, name="Ownerless Profile")
    with pytest.raises(ValueError, match="user_id must be a positive integer"):
        append_insight(None, "Ownerless insight")

    db = in_memory_db()
    rows = db.query(Strategy).all()
    db.close()
    assert len(rows) == 1
    assert rows[0].user_id is None
    assert rows[0].name == "Legacy Profile"
    assert rows[0].risk_rules == "Legacy risk rule"


@pytest.mark.parametrize("invalid_user_id", [0, -1, True, "1"])
def test_strategy_operations_require_a_positive_integer_user_id(
    in_memory_db, invalid_user_id
):
    from src.tradelens.services.strategy import (
        append_insight,
        get_active_strategy,
        upsert_strategy_profile,
    )

    operations = (
        lambda: get_active_strategy(invalid_user_id),
        lambda: upsert_strategy_profile(invalid_user_id, name="Invalid owner"),
        lambda: append_insight(invalid_user_id, "Invalid owner insight"),
    )

    for operation in operations:
        with pytest.raises(ValueError, match="user_id must be a positive integer"):
            operation()


def test_create_strategy_creates_active_profile(in_memory_db):
    from src.tradelens.services.strategy import upsert_strategy_profile

    result = upsert_strategy_profile(
        1, name="ICT OB Strategy", entry_rules="BOS + OB retest"
    )

    assert result["name"] == "ICT OB Strategy"
    assert result["entry_rules"] == "BOS + OB retest"
    assert result["is_active"] == 1
    assert result["created_at"] is not None
    assert result["updated_at"] is not None

    db = in_memory_db()
    rows = db.query(Strategy).all()
    db.close()
    assert len(rows) == 1
    assert rows[0].is_active == 1


def test_upsert_updates_existing_active_profile(in_memory_db):
    from src.tradelens.services.strategy import upsert_strategy_profile

    upsert_strategy_profile(1, name="Initial", entry_rules="Rule A")
    result = upsert_strategy_profile(
        1, name="Updated", entry_rules="Rule B", risk_rules="Max 1%"
    )

    assert result["name"] == "Updated"
    assert result["entry_rules"] == "Rule B"
    assert result["risk_rules"] == "Max 1%"
    assert result["is_active"] == 1

    db = in_memory_db()
    rows = db.query(Strategy).all()
    db.close()
    assert len(rows) == 1  # still one row, not two


def test_only_one_active_profile_at_a_time(in_memory_db):
    """If multiple rows somehow exist, upsert ensures only one is active."""
    db = in_memory_db()
    db.add(Strategy(name="Old A", user_id=1, is_active=1))
    db.add(Strategy(name="Old B", user_id=1, is_active=1))
    db.commit()
    db.close()

    from src.tradelens.services.strategy import upsert_strategy_profile

    upsert_strategy_profile(1, name="New Active")

    db2 = in_memory_db()
    active_rows = (
        db2.query(Strategy).filter(Strategy.user_id == 1, Strategy.is_active == 1).all()
    )
    db2.close()

    assert len(active_rows) == 1
    assert active_rows[0].name == "New Active"


def test_get_active_strategy_returns_dict(in_memory_db):
    from src.tradelens.services.strategy import (
        get_active_strategy,
        upsert_strategy_profile,
    )

    upsert_strategy_profile(
        1,
        name="ICT",
        trading_style="Smart Money",
        entry_rules="OB retest",
        markets="NQ, ES",
    )

    result = get_active_strategy(1)

    assert result is not None
    assert isinstance(result, dict)
    assert result["name"] == "ICT"
    assert result["trading_style"] == "Smart Money"
    assert result["markets"] == "NQ, ES"
    assert result["is_active"] == 1


def test_get_active_strategy_returns_none_when_no_profile(in_memory_db):
    from src.tradelens.services.strategy import get_active_strategy

    result = get_active_strategy(1)
    assert result is None


def test_get_active_strategy_returns_none_when_all_inactive(in_memory_db):
    """A row with is_active=0 should NOT be returned."""
    db = in_memory_db()
    db.add(Strategy(name="Inactive", user_id=1, is_active=0))
    db.commit()
    db.close()

    from src.tradelens.services.strategy import get_active_strategy

    result = get_active_strategy(1)
    assert result is None


def test_upsert_sets_timestamps_properly(in_memory_db):
    from src.tradelens.services.strategy import upsert_strategy_profile

    result = upsert_strategy_profile(1, name="TS Test")

    assert result["created_at"] is not None
    assert result["updated_at"] is not None
    assert result["created_at"] <= result["updated_at"]


# ---------------------------------------------------------------------------
# append_insight (Week 5 Phase 3) — add a pattern's suggested rule to the profile
# ---------------------------------------------------------------------------


def test_append_insight_creates_profile_when_none(in_memory_db):
    from src.tradelens.services.strategy import append_insight

    result = append_insight(1, "Wait 15 minutes after a loss before re-entering.")

    assert result["is_active"] == 1
    assert "Wait 15 minutes after a loss" in result["risk_rules"]

    db = in_memory_db()
    rows = (
        db.query(Strategy).filter(Strategy.user_id == 1, Strategy.is_active == 1).all()
    )
    db.close()
    assert len(rows) == 1


def test_append_insight_preserves_existing_content(in_memory_db):
    from src.tradelens.services.strategy import append_insight, upsert_strategy_profile

    upsert_strategy_profile(1, name="ICT", risk_rules="Max 1% risk per trade")
    result = append_insight(1, "Wait 15 minutes after a loss.")

    assert "Max 1% risk per trade" in result["risk_rules"]
    assert "Wait 15 minutes after a loss." in result["risk_rules"]


def test_append_insight_appends_each_on_its_own_line(in_memory_db):
    from src.tradelens.services.strategy import append_insight

    append_insight(1, "First discipline rule.")
    result = append_insight(1, "Second discipline rule.")

    lines = [ln for ln in result["risk_rules"].splitlines() if ln.strip()]
    assert len(lines) == 2
    assert "First discipline rule." in result["risk_rules"]
    assert "Second discipline rule." in result["risk_rules"]


def test_append_insight_custom_field(in_memory_db):
    from src.tradelens.services.strategy import append_insight

    result = append_insight(
        1, "Stops getting moved on losers.", field="common_mistakes"
    )

    assert "Stops getting moved on losers." in result["common_mistakes"]


def test_append_insight_blank_is_noop(in_memory_db):
    from src.tradelens.services.strategy import append_insight, upsert_strategy_profile

    upsert_strategy_profile(1, name="ICT", risk_rules="Max 1% risk")
    result = append_insight(1, "   ")

    assert result["risk_rules"] == "Max 1% risk"


def test_append_insight_invalid_field_raises(in_memory_db):
    from src.tradelens.services.strategy import append_insight

    with pytest.raises(ValueError, match="Unknown strategy field"):
        append_insight(1, "x", field="not_a_field")
