"""
Session E (P4): sample trades must be dated recently so they appear on the
Dashboard and inside default date ranges (Analytics last-90-days, this week).
"""

import datetime as dt

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import src.tradelens.services.sample_data as sample_data
from src.tradelens.db.models import Base, Trade


@pytest.fixture
def in_memory_db(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    InMemorySession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(sample_data, "SessionLocal", InMemorySession)
    yield InMemorySession
    Base.metadata.drop_all(engine)


def test_samples_are_recent_and_not_future(in_memory_db):
    sample_data.load_sample_trades(user_id=1)
    db = in_memory_db()
    try:
        dates = sorted(
            dt.date.fromisoformat(t.trade_date)
            for t in db.query(Trade).filter(Trade.is_sample == 1)
        )
    finally:
        db.close()

    today = dt.date.today()
    assert dates, "no sample trades were inserted"
    # Never future-dated, and the most recent lands within the current week.
    assert dates[-1] <= today
    assert (today - dates[-1]).days <= 3
    # The whole set sits comfortably inside a 90-day window.
    assert (today - dates[0]).days <= 90
    # Weekdays only.
    assert all(d.weekday() < 5 for d in dates)
