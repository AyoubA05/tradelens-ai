"""Server-side strategy_used derivation on the create_trade path.

The Next.js form omits strategy_used entirely (unlike the Streamlit page,
which derives it from the owner's active Strategy Profile via
`_build_trade_data`'s `(_strategy or {}).get("name")` and passes it
explicitly). `strategy_used` is a Journal filter (`get_trades`'s `strategy`
kwarg), so a trade created without it silently fails to match a strategy
filter the trader uses to find their own trades.

`create_trade` must fill it in itself, server-side, from the owner's active
Strategy Profile — never trust the browser to assert which strategy is
active, same reasoning as the session/killzone derivation in
test_trade_service_session_derivation.py.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import src.tradelens.services.strategy as strategy_service
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
    # the owner's active profile through strategy.get_active_strategy.
    monkeypatch.setattr(trade_service, "SessionLocal", TestSession)
    monkeypatch.setattr(strategy_service, "SessionLocal", TestSession, raising=False)
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


def test_active_strategy_name_fills_strategy_used(two_users):
    owner, _ = two_users
    strategy_service.upsert_strategy_profile(owner, name="ICT OB Continuation")

    trade = _create({"asset": "NQ", "trade_date": "2026-01-15"}, owner)

    assert trade.strategy_used == "ICT OB Continuation"


def test_no_active_strategy_still_creates_with_null_strategy_used(two_users):
    owner, _ = two_users

    trade = _create({"asset": "NQ", "trade_date": "2026-01-15"}, owner)

    assert trade.id is not None
    assert trade.strategy_used is None


def test_explicit_strategy_used_from_caller_is_preserved(two_users):
    """Streamlit path parity: create_trade must never overwrite a caller's
    already-derived value, even though the owner has a different active
    profile."""
    owner, _ = two_users
    strategy_service.upsert_strategy_profile(owner, name="ICT OB Continuation")

    trade = _create(
        {
            "asset": "NQ",
            "trade_date": "2026-01-15",
            "strategy_used": "Caller Supplied Value",
        },
        owner,
    )

    assert trade.strategy_used == "Caller Supplied Value"
