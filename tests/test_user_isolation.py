import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import src.tradelens.services.trade_service as trade_service
from src.tradelens.db.models import Base, User
from src.tradelens.services.trade_service import (
    create_trade,
    delete_trade,
    get_trade,
    get_trades,
    update_trade,
)


@pytest.fixture
def in_memory_db(monkeypatch):
    """Redirect trade service sessions to an isolated SQLite database."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(trade_service, "SessionLocal", session_factory)
    yield session_factory
    Base.metadata.drop_all(engine)


@pytest.fixture
def two_user_trades(in_memory_db):
    db = in_memory_db()
    user_a = User(username="alice", password_hash="hash-a")
    user_b = User(username="bob", password_hash="hash-b")
    db.add_all([user_a, user_b])
    db.commit()
    db.refresh(user_a)
    db.refresh(user_b)
    db.close()

    trade_a = create_trade(
        {"asset": "NQ", "trade_date": "2026-07-01", "user_id": user_a.id}
    )
    return user_a, user_b, trade_a


def test_user_cannot_read_update_or_delete_another_users_trade(two_user_trades):
    user_a, user_b, trade_a = two_user_trades

    assert get_trade(trade_a.id, user_id=user_b.id) is None
    assert update_trade(trade_a.id, user_id=user_b.id, notes="changed") is None
    assert not delete_trade(trade_a.id, user_id=user_b.id)
    assert get_trade(trade_a.id, user_id=user_a.id).notes != "changed"


def test_same_owner_can_read_update_and_delete_trade(two_user_trades):
    user_a, _, trade_a = two_user_trades

    assert get_trade(trade_a.id, user_id=user_a.id).id == trade_a.id
    assert (
        update_trade(trade_a.id, user_id=user_a.id, notes="changed").notes == "changed"
    )
    assert delete_trade(trade_a.id, user_id=user_a.id)
    assert get_trade(trade_a.id, user_id=user_a.id) is None


def test_registered_user_does_not_receive_null_owned_legacy_rows(two_user_trades):
    user_a, _, trade_a = two_user_trades
    create_trade({"asset": "ES", "trade_date": "2026-07-02", "user_id": None})

    assert [trade.id for trade in get_trades(user_id=user_a.id)] == [trade_a.id]


def test_explicit_none_scopes_to_null_owned_legacy_rows(two_user_trades):
    _, _, trade_a = two_user_trades
    legacy_trade = create_trade(
        {"asset": "ES", "trade_date": "2026-07-02", "user_id": None}
    )

    assert [trade.id for trade in get_trades(user_id=None)] == [legacy_trade.id]
    assert get_trade(legacy_trade.id, user_id=None).id == legacy_trade.id
    assert get_trade(trade_a.id, user_id=None) is None


def test_direct_trade_operations_require_an_owner_argument(two_user_trades):
    _, _, trade_a = two_user_trades

    with pytest.raises(TypeError):
        get_trade(trade_a.id)
    with pytest.raises(TypeError):
        update_trade(trade_a.id, notes="changed")
    with pytest.raises(TypeError):
        delete_trade(trade_a.id)


def test_update_trade_cannot_reassign_owner_or_id(two_user_trades):
    user_a, user_b, trade_a = two_user_trades

    updated = update_trade(trade_a.id, user_id=user_a.id, id=999, notes="changed")

    assert updated.id == trade_a.id
    assert updated.user_id == user_a.id
    assert updated.notes == "changed"

    with pytest.raises(TypeError):
        update_trade(trade_a.id, user_a.id, **{"user_id": user_b.id, "notes": "stolen"})

    reread = get_trade(trade_a.id, user_id=user_a.id)
    assert reread.user_id == user_a.id
    assert reread.notes == "changed"
