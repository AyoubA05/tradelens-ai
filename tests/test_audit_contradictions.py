"""Counting the contradictory rows that predate write-time validation.

New writes are blocked, and metrics read old rows coherently, but neither
tells the operator whether any contradictions are actually stored. The
beta scorecard requires that count to be zero, so something has to be able
to produce it.

Reporting is separate from repairing: the plan's rule is that legacy rows
are never silently rewritten, so a fix happens only when explicitly asked
for and says exactly what it changed.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import scripts.audit_contradictions as audit
from src.tradelens.db.models import Base, Trade


@pytest.fixture
def db_factory(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(audit, "SessionLocal", Session)
    yield Session
    Base.metadata.drop_all(engine)


def _add(db, **kw):
    db.add(Trade(**{"trade_date": "2026-07-20", "asset": "NQ", **kw}))
    db.commit()


def test_a_clean_database_reports_no_contradictions(db_factory):
    db = db_factory()
    _add(db, result="Win", pnl=250.0)
    _add(db, result="Loss", pnl=-100.0)
    _add(db, result="Breakeven", pnl=0.0)
    db.close()
    assert audit.find_contradictions() == []


def test_a_win_with_negative_pnl_is_reported(db_factory):
    """The exact record the audit found in production screenshots."""
    db = db_factory()
    _add(db, result="Win", pnl=-500.0)
    db.close()

    found = audit.find_contradictions()
    assert len(found) == 1
    assert found[0].stored_result == "Win"
    assert found[0].pnl == -500.0
    assert found[0].expected_result == "Loss"


def test_rows_without_pnl_are_not_contradictions(db_factory):
    """A manual outcome with no P&L is allowed, not a conflict."""
    db = db_factory()
    _add(db, result="Win", pnl=None)
    db.close()
    assert audit.find_contradictions() == []


def test_rows_without_a_result_are_not_contradictions(db_factory):
    db = db_factory()
    _add(db, result=None, pnl=-500.0)
    db.close()
    assert audit.find_contradictions() == []


def test_a_zero_pnl_labelled_win_is_reported(db_factory):
    db = db_factory()
    _add(db, result="Win", pnl=0.0)
    db.close()
    found = audit.find_contradictions()
    assert len(found) == 1
    assert found[0].expected_result == "Breakeven"


def test_the_report_names_the_owner_so_support_can_act(db_factory):
    db = db_factory()
    _add(db, result="Win", pnl=-500.0, user_id=7)
    db.close()
    assert audit.find_contradictions()[0].user_id == 7


# --- repair is opt-in -------------------------------------------------------


def test_auditing_never_rewrites_a_row(db_factory):
    """Reporting must be read-only; the plan forbids silent rewrites."""
    db = db_factory()
    _add(db, result="Win", pnl=-500.0)
    db.close()

    audit.find_contradictions()

    db = db_factory()
    try:
        assert db.query(Trade).first().result == "Win"
    finally:
        db.close()


def test_repair_sets_the_label_the_money_supports(db_factory):
    db = db_factory()
    _add(db, result="Win", pnl=-500.0)
    db.close()

    changed = audit.repair_contradictions()
    assert changed == 1

    db = db_factory()
    try:
        assert db.query(Trade).first().result == "Loss"
    finally:
        db.close()
    assert audit.find_contradictions() == []


def test_repair_leaves_coherent_rows_alone(db_factory):
    db = db_factory()
    _add(db, result="Win", pnl=250.0)
    _add(db, result="Win", pnl=-500.0)
    db.close()

    assert audit.repair_contradictions() == 1

    db = db_factory()
    try:
        results = sorted(t.result for t in db.query(Trade).all())
        assert results == ["Loss", "Win"]
    finally:
        db.close()


def test_repair_on_a_clean_database_changes_nothing(db_factory):
    db = db_factory()
    _add(db, result="Loss", pnl=-100.0)
    db.close()
    assert audit.repair_contradictions() == 0


# --- reporting format -------------------------------------------------------


def test_the_summary_states_the_count_plainly(db_factory):
    db = db_factory()
    _add(db, result="Win", pnl=-500.0)
    db.close()
    text = audit.format_report(audit.find_contradictions())
    assert "1" in text
    assert "Win" in text and "Loss" in text


def test_a_clean_summary_says_so(db_factory):
    assert "No contradictory" in audit.format_report([])
