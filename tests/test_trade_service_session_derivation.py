"""Server-side session/killzone derivation on POST /v1/trades' create path.

The Next.js form omits session/killzone (unlike the Streamlit page,
which derives and passes them explicitly), so `create_trade` must fill them
in itself from entry_time + trade_date + the OWNER's stored timezone —
never a server default or a request-supplied zone, since that would
silently corrupt which killzone a trade is attributed to.
"""

from __future__ import annotations

from datetime import datetime, timezone as dt_timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import src.tradelens.services.app_settings as app_settings
import src.tradelens.services.trade_service as trade_service
from src.tradelens.db.models import Base, User


@pytest.fixture
def in_memory_db(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    # Both services must share the same in-memory DB — create_trade reads
    # the owner's timezone through app_settings.get_timezone.
    monkeypatch.setattr(trade_service, "SessionLocal", TestSession)
    monkeypatch.setattr(app_settings, "SessionLocal", TestSession, raising=False)
    yield TestSession
    Base.metadata.drop_all(engine)


@pytest.fixture
def two_users(in_memory_db):
    db = in_memory_db()
    alice = User(username="alice", password_hash="hash")
    bob = User(username="bob", password_hash="hash")
    db.add_all([alice, bob])
    db.commit()
    db.refresh(alice)
    db.refresh(bob)
    db.close()
    return alice.id, bob.id


def _create(data, user_id):
    return trade_service.create_trade(data, user_id=user_id)


def test_derives_session_and_killzone_for_owner_timezone(two_users):
    owner, _ = two_users
    app_settings.set_timezone(owner, "America/New_York")

    trade = _create(
        {
            "asset": "NQ",
            "trade_date": "2026-01-15",
            "entry_time": "09:30",
        },
        owner,
    )

    assert trade.session == "New York Open"
    assert trade.killzone == "ny_am"


def test_different_owner_timezone_yields_different_killzone(two_users):
    owner, other = two_users
    app_settings.set_timezone(owner, "America/New_York")
    # A trader whose stored zone is far enough away that the identical
    # instant lands in a different killzone/session window once converted
    # to local wall-clock. Only a tz-*aware* entry_time actually exercises
    # the conversion in `_coerce_local_time` — a naive 'HH:MM' string is
    # taken as already-local and would pass regardless of which timezone
    # (or none) is used, defeating the point of this assertion.
    app_settings.set_timezone(other, "Asia/Tokyo")

    identical_instant = datetime(2026, 1, 15, 14, 30, tzinfo=dt_timezone.utc)

    trade_owner = _create(
        {"asset": "NQ", "trade_date": "2026-01-15", "entry_time": identical_instant},
        owner,
    )
    trade_other = _create(
        {"asset": "NQ", "trade_date": "2026-01-15", "entry_time": identical_instant},
        other,
    )

    assert trade_owner.killzone != trade_other.killzone
    assert trade_owner.session != trade_other.session


def test_missing_entry_time_leaves_session_and_killzone_null(two_users):
    """No entry time means the derivation has nothing to derive FROM.

    "Off-Hours"/"off_session" is a statement about the trade — that it was
    entered outside session hours — and asserting it from an absent
    entry_time invents a fact. These fields drive the Journal session filter
    and Overview's killzone panel, so a fabricated value is indistinguishable
    from a recorded one. Unknown stays NULL.
    """
    owner, _ = two_users
    app_settings.set_timezone(owner, "America/New_York")

    trade = _create({"asset": "NQ", "trade_date": "2026-01-15"}, owner)

    assert trade.id is not None
    assert trade.session is None
    assert trade.killzone is None


def test_explicit_session_and_killzone_from_caller_are_preserved(two_users):
    """Streamlit path parity: create_trade must never overwrite a caller's
    already-derived values, even though the owner's timezone would derive
    something different."""
    owner, _ = two_users
    app_settings.set_timezone(owner, "America/New_York")

    trade = _create(
        {
            "asset": "NQ",
            "trade_date": "2026-01-15",
            "entry_time": "09:30",
            "session": "Custom Session",
            "killzone": "custom_killzone",
        },
        owner,
    )

    assert trade.session == "Custom Session"
    assert trade.killzone == "custom_killzone"
