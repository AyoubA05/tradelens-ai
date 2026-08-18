"""Class A: functions that returned rows across tenant boundaries.

Each test seeds two users and asserts that the function cannot be induced to
see the other user's row — and that omitting the owner raises rather than
quietly widening the query.
"""
import pytest

from src.tradelens.services import trade_service, weekly


def _trade(user_id, asset="NQ", date="2026-08-12"):
    return {
        "user_id": user_id,
        "trade_date": date,
        "asset": asset,
        "session": "New York Open",
        "setup_type": "Liquidity Sweep + FVG",
        "result": "Win",
        "pnl": 100.0,
    }


def test_get_trades_requires_an_owner():
    with pytest.raises(TypeError):
        trade_service.get_trades()


def test_get_trades_refuses_a_null_owner():
    with pytest.raises(ValueError):
        trade_service.get_trades(user_id=None)


def test_get_trades_returns_only_the_owners_rows(two_users):
    a, b = two_users
    trade_service.create_trade(_trade(a))
    trade_service.create_trade(_trade(b))

    rows = trade_service.get_trades(user_id=a)

    assert len(rows) == 1
    assert all(t.user_id == a for t in rows)


def test_trade_hash_exists_requires_an_owner():
    with pytest.raises(ValueError):
        trade_service.trade_hash_exists("abc", None)


def test_trade_hash_does_not_leak_across_users(two_users):
    """An identical setup logged by another trader is not this trader's duplicate."""
    a, b = two_users
    created = trade_service.create_trade(_trade(b))

    assert trade_service.trade_hash_exists(created.trade_hash, a) is False
    assert trade_service.trade_hash_exists(created.trade_hash, b) is True


def test_find_recent_duplicate_requires_an_owner():
    with pytest.raises(ValueError):
        trade_service.find_recent_duplicate(_trade(1), None)


def test_find_recent_duplicate_never_returns_another_users_trade(two_users):
    a, b = two_users
    trade_service.create_trade(_trade(b))

    assert trade_service.find_recent_duplicate(_trade(a), a) is None


def test_list_weekly_reviews_is_gone():
    """It had no owner parameter at all, so every call was cross-tenant."""
    assert not hasattr(weekly, "list_weekly_reviews")
