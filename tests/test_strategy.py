"""
Tests for strategy.py — all DB operations use in-memory SQLite.
"""
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.tradelens.db.models import Base, Strategy


# ---------------------------------------------------------------------------
# Fixture
# ---------------------------------------------------------------------------

@pytest.fixture()
def in_memory_db(monkeypatch):
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr("src.tradelens.services.strategy.SessionLocal", TestSession)
    return TestSession


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_create_strategy_creates_active_profile(in_memory_db):
    from src.tradelens.services.strategy import upsert_strategy_profile

    result = upsert_strategy_profile(name="ICT OB Strategy", entry_rules="BOS + OB retest")

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

    upsert_strategy_profile(name="Initial", entry_rules="Rule A")
    result = upsert_strategy_profile(name="Updated", entry_rules="Rule B", risk_rules="Max 1%")

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
    db.add(Strategy(name="Old A", is_active=1))
    db.add(Strategy(name="Old B", is_active=1))
    db.commit()
    db.close()

    from src.tradelens.services.strategy import upsert_strategy_profile

    upsert_strategy_profile(name="New Active")

    db2 = in_memory_db()
    active_rows = db2.query(Strategy).filter(Strategy.is_active == 1).all()
    db2.close()

    assert len(active_rows) == 1
    assert active_rows[0].name == "New Active"


def test_get_active_strategy_returns_dict(in_memory_db):
    from src.tradelens.services.strategy import get_active_strategy, upsert_strategy_profile

    upsert_strategy_profile(
        name="ICT",
        trading_style="Smart Money",
        entry_rules="OB retest",
        markets="NQ, ES",
    )

    result = get_active_strategy()

    assert result is not None
    assert isinstance(result, dict)
    assert result["name"] == "ICT"
    assert result["trading_style"] == "Smart Money"
    assert result["markets"] == "NQ, ES"
    assert result["is_active"] == 1


def test_get_active_strategy_returns_none_when_no_profile(in_memory_db):
    from src.tradelens.services.strategy import get_active_strategy

    result = get_active_strategy()
    assert result is None


def test_get_active_strategy_returns_none_when_all_inactive(in_memory_db):
    """A row with is_active=0 should NOT be returned."""
    db = in_memory_db()
    db.add(Strategy(name="Inactive", is_active=0))
    db.commit()
    db.close()

    from src.tradelens.services.strategy import get_active_strategy

    result = get_active_strategy()
    assert result is None


def test_upsert_sets_timestamps_properly(in_memory_db):
    from src.tradelens.services.strategy import upsert_strategy_profile

    result = upsert_strategy_profile(name="TS Test")

    assert result["created_at"] is not None
    assert result["updated_at"] is not None
    assert result["created_at"] <= result["updated_at"]


# ---------------------------------------------------------------------------
# append_insight (Week 5 Phase 3) — add a pattern's suggested rule to the profile
# ---------------------------------------------------------------------------

def test_append_insight_creates_profile_when_none(in_memory_db):
    from src.tradelens.services.strategy import append_insight

    result = append_insight("Wait 15 minutes after a loss before re-entering.")

    assert result["is_active"] == 1
    assert "Wait 15 minutes after a loss" in result["risk_rules"]

    db = in_memory_db()
    rows = db.query(Strategy).filter(Strategy.is_active == 1).all()
    db.close()
    assert len(rows) == 1


def test_append_insight_preserves_existing_content(in_memory_db):
    from src.tradelens.services.strategy import append_insight, upsert_strategy_profile

    upsert_strategy_profile(name="ICT", risk_rules="Max 1% risk per trade")
    result = append_insight("Wait 15 minutes after a loss.")

    assert "Max 1% risk per trade" in result["risk_rules"]
    assert "Wait 15 minutes after a loss." in result["risk_rules"]


def test_append_insight_appends_each_on_its_own_line(in_memory_db):
    from src.tradelens.services.strategy import append_insight

    append_insight("First discipline rule.")
    result = append_insight("Second discipline rule.")

    lines = [ln for ln in result["risk_rules"].splitlines() if ln.strip()]
    assert len(lines) == 2
    assert "First discipline rule." in result["risk_rules"]
    assert "Second discipline rule." in result["risk_rules"]


def test_append_insight_custom_field(in_memory_db):
    from src.tradelens.services.strategy import append_insight

    result = append_insight("Stops getting moved on losers.", field="common_mistakes")

    assert "Stops getting moved on losers." in result["common_mistakes"]


def test_append_insight_blank_is_noop(in_memory_db):
    from src.tradelens.services.strategy import append_insight, upsert_strategy_profile

    upsert_strategy_profile(name="ICT", risk_rules="Max 1% risk")
    result = append_insight("   ")

    assert result["risk_rules"] == "Max 1% risk"


def test_append_insight_invalid_field_raises(in_memory_db):
    from src.tradelens.services.strategy import append_insight

    with pytest.raises(ValueError, match="Unknown strategy field"):
        append_insight("x", field="not_a_field")
