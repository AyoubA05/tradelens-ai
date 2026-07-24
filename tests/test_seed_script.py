"""Seeded demo data must be coherent and visible.

scripts/seed.py fills the demo/marketing database. Two properties matter:
rows must satisfy the same outcome rule the app enforces at write time, and
they must be dated recently enough to fall inside the app's default windows
(the Dashboard's week, Analytics' last 90 days) — the same rule
test_sample_recency.py pins for the sample_data service.
"""

import datetime as dt
import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.tradelens.db.models import Base, Trade
from src.tradelens.services.trade_validation import OutcomeMismatch, canonical_outcome

ROOT = Path(__file__).resolve().parents[1]


def _load_seed():
    spec = importlib.util.spec_from_file_location(
        "seed_mod", ROOT / "scripts" / "seed.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def seeded(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    InMemorySession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    seed = _load_seed()
    monkeypatch.setattr(seed, "SessionLocal", InMemorySession)
    seed.seed()
    yield InMemorySession
    Base.metadata.drop_all(engine)


def test_no_seeded_row_contradicts_its_pnl(seeded):
    db = seeded()
    try:
        for row in db.query(Trade).all():
            try:
                canonical_outcome(row.result, row.pnl)
            except (OutcomeMismatch, ValueError) as exc:  # pragma: no cover
                pytest.fail(f"trade {row.id}: {exc}")
    finally:
        db.close()


def test_seeded_rows_use_the_canonical_outcome_labels(seeded):
    db = seeded()
    try:
        labels = {row.result for row in db.query(Trade).all()}
        assert labels <= {"Win", "Loss", "Breakeven"}, labels
    finally:
        db.close()


def test_seeded_trades_are_recent_and_not_in_the_future(seeded):
    """A fixed start date silently ages out of every default filter."""
    db = seeded()
    try:
        dates = sorted(
            dt.date.fromisoformat(r.trade_date) for r in db.query(Trade).all()
        )
    finally:
        db.close()

    today = dt.date.today()
    assert dates, "seed produced no trades"
    assert dates[-1] <= today, "seeded a future trade"
    # Newest inside the Dashboard's week, oldest inside Analytics' 90 days.
    assert (today - dates[-1]).days <= 7
    assert (today - dates[0]).days <= 90
