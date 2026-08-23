"""`trade_service.list_trades` — filtering, pagination, and total.

`get_trades` has no pagination and is left untouched; `list_trades` is a
genuinely new function. The properties under test: total and page come from
one shared filter construction (they cannot silently drift), limit/offset are
clamped server-side, ordering is `trade_date desc, id desc` so it is total
(the existing `get_trades` order is a single key and same-day ties are
non-deterministic under it), and a second owner's rows are never reachable.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import src.tradelens.services.trade_service as trade_service
from src.tradelens.db.models import Base


def _create(data, user_id=1):
    return trade_service.create_trade(data, user_id=user_id)


@pytest.fixture
def in_memory_db(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    InMemorySession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(trade_service, "SessionLocal", InMemorySession)
    yield
    Base.metadata.drop_all(engine)


def test_list_trades_never_returns_another_owner_s_rows(in_memory_db):
    _create({"asset": "NQ", "trade_date": "2026-01-01"}, user_id=1)
    _create({"asset": "ES", "trade_date": "2026-01-02"}, user_id=2)

    page = trade_service.list_trades(user_id=1)
    assert [t.asset for t in page.trades] == ["NQ"]
    assert page.total == 1


def test_list_trades_filters_by_asset(in_memory_db):
    _create({"asset": "NQ", "trade_date": "2026-01-01"})
    _create({"asset": "ES", "trade_date": "2026-01-02"})

    page = trade_service.list_trades(user_id=1, asset="NQ")
    assert [t.asset for t in page.trades] == ["NQ"]
    assert page.total == 1


def test_list_trades_asset_filter_is_exact_not_a_substring_match(in_memory_db):
    """`NQ` must not also return MNQ.

    A substring filter narrows to something other than what its name says,
    and it does so in the total as well as the rows — so a trader reviewing
    NQ sees micros folded into their count. Every other filter here is
    exact; this one has to be too.
    """
    _create({"asset": "NQ", "trade_date": "2026-01-01"})
    _create({"asset": "MNQ", "trade_date": "2026-01-02"})
    _create({"asset": "NQZ5", "trade_date": "2026-01-03"})

    page = trade_service.list_trades(user_id=1, asset="NQ")
    assert [t.asset for t in page.trades] == ["NQ"]
    assert page.total == 1


def test_list_trades_asset_filter_treats_a_wildcard_as_a_literal(in_memory_db):
    """Under `ilike('%..%')` an asset of `%` matched the entire journal."""
    _create({"asset": "NQ", "trade_date": "2026-01-01"})
    _create({"asset": "ES", "trade_date": "2026-01-02"})

    page = trade_service.list_trades(user_id=1, asset="%")
    assert page.trades == []
    assert page.total == 0


def test_list_trades_filters_by_session(in_memory_db):
    _create({"asset": "NQ", "trade_date": "2026-01-01", "session": "ny_am"})
    _create({"asset": "NQ", "trade_date": "2026-01-02", "session": "london_open"})

    page = trade_service.list_trades(user_id=1, session="ny_am")
    assert page.total == 1
    assert page.trades[0].session == "ny_am"


def test_list_trades_filters_by_setup_type(in_memory_db):
    _create({"asset": "NQ", "trade_date": "2026-01-01", "setup_type": "FVG"})
    _create({"asset": "NQ", "trade_date": "2026-01-02", "setup_type": "OB"})

    page = trade_service.list_trades(user_id=1, setup_type="FVG")
    assert page.total == 1
    assert page.trades[0].setup_type == "FVG"


def test_list_trades_filters_by_result(in_memory_db):
    _create({"asset": "NQ", "trade_date": "2026-01-01", "result": "Win", "pnl": 100.0})
    _create({"asset": "NQ", "trade_date": "2026-01-02", "result": "Loss", "pnl": -50.0})

    page = trade_service.list_trades(user_id=1, result="Win")
    assert page.total == 1
    assert page.trades[0].result == "Win"


def test_list_trades_filters_by_date_range(in_memory_db):
    _create({"asset": "NQ", "trade_date": "2026-01-01"})
    _create({"asset": "NQ", "trade_date": "2026-01-15"})
    _create({"asset": "NQ", "trade_date": "2026-02-01"})

    page = trade_service.list_trades(
        user_id=1, start_date="2026-01-10", end_date="2026-01-31"
    )
    assert page.total == 1
    assert page.trades[0].trade_date == "2026-01-15"


def test_list_trades_combined_filters_intersect(in_memory_db):
    _create(
        {
            "asset": "NQ",
            "trade_date": "2026-01-01",
            "session": "ny_am",
            "result": "Win",
            "pnl": 100.0,
        }
    )
    _create(
        {
            "asset": "NQ",
            "trade_date": "2026-01-02",
            "session": "ny_am",
            "result": "Loss",
            "pnl": -50.0,
        }
    )
    _create(
        {
            "asset": "ES",
            "trade_date": "2026-01-03",
            "session": "ny_am",
            "result": "Win",
            "pnl": 75.0,
        }
    )

    page = trade_service.list_trades(
        user_id=1, asset="NQ", session="ny_am", result="Win"
    )
    assert page.total == 1
    assert page.trades[0].pnl == 100.0


def test_list_trades_total_counts_filtered_set_not_the_page(in_memory_db):
    for i in range(5):
        _create({"asset": "NQ", "trade_date": f"2026-01-{i + 1:02d}"})

    page = trade_service.list_trades(user_id=1, limit=2, offset=0)
    assert page.total == 5
    assert len(page.trades) == 2


def test_list_trades_page_zero(in_memory_db):
    for i in range(3):
        _create({"asset": "NQ", "trade_date": f"2026-01-{i + 1:02d}"})

    page = trade_service.list_trades(user_id=1, limit=2, offset=0)
    assert len(page.trades) == 2
    assert page.limit == 2
    assert page.offset == 0


def test_list_trades_last_page_is_partial(in_memory_db):
    for i in range(5):
        _create({"asset": "NQ", "trade_date": f"2026-01-{i + 1:02d}"})

    page = trade_service.list_trades(user_id=1, limit=2, offset=4)
    assert len(page.trades) == 1
    assert page.total == 5


def test_list_trades_offset_beyond_the_end_is_empty_not_an_error(in_memory_db):
    _create({"asset": "NQ", "trade_date": "2026-01-01"})

    page = trade_service.list_trades(user_id=1, limit=10, offset=100)
    assert page.trades == []
    assert page.total == 1


def test_list_trades_filter_matching_nothing_returns_empty_and_zero_total(
    in_memory_db,
):
    _create({"asset": "NQ", "trade_date": "2026-01-01"})

    page = trade_service.list_trades(user_id=1, asset="GBPUSD")
    assert page.trades == []
    assert page.total == 0


@pytest.mark.parametrize(
    ("requested", "expected"),
    [(0, 1), (101, 100), (-1, 1), (50, 50)],
)
def test_list_trades_clamps_limit_server_side(in_memory_db, requested, expected):
    for i in range(3):
        _create({"asset": "NQ", "trade_date": f"2026-01-{i + 1:02d}"})

    page = trade_service.list_trades(user_id=1, limit=requested)
    assert page.limit == expected


def test_list_trades_clamps_negative_offset_to_zero(in_memory_db):
    _create({"asset": "NQ", "trade_date": "2026-01-01"})

    page = trade_service.list_trades(user_id=1, offset=-5)
    assert page.offset == 0


def test_list_trades_clamp_bounds_the_ROWS_not_only_the_reported_limit(in_memory_db):
    """The clamp is a security property, so assert what came back.

    Asserting `page.limit` alone tests a number the service reports about
    itself. An implementation that reported the clamped value while querying
    with the raw one would pass that — and a caller asking for `limit=100000`
    would get the whole table, which is exactly what the clamp exists to
    prevent. The row count is the only assertion that can tell those apart.
    """
    for i in range(105):
        _create({"asset": "NQ", "trade_date": "2026-01-01", "pnl": float(i)})

    page = trade_service.list_trades(user_id=1, limit=100000)

    assert page.limit == 100
    assert len(page.trades) == 100, "a caller must not be able to request everything"
    assert page.total == 105, "the total still describes the whole filtered set"


def test_list_trades_offset_actually_skips_rows(in_memory_db):
    """`offset` must move the window, not merely be echoed back."""
    ids = [
        _create({"asset": "NQ", "trade_date": "2026-01-01", "pnl": float(i)}).id
        for i in range(5)
    ]
    newest_first = sorted(ids, reverse=True)

    page = trade_service.list_trades(user_id=1, limit=2, offset=2)

    assert page.offset == 2
    assert [t.id for t in page.trades] == newest_first[2:4]


def test_list_trades_stable_order_across_same_day_ties(in_memory_db):
    """Ordering by trade_date alone is a partial order: three same-day trades
    could land on two pages or none. `id` breaks the tie so paging is total.

    The assertion is the SEQUENCE, not the set. Set-equality plus a
    no-duplicates check survives dropping the `id` tiebreaker entirely,
    because SQLite happens to hand back rowid order when the ORDER BY does
    not decide — so the test would pass while the ordering is genuinely
    partial and another engine (or another plan) reorders the ties.
    """
    ids = [
        _create({"asset": "NQ", "trade_date": "2026-01-01", "pnl": float(i)}).id
        for i in range(3)
    ]
    newest_first = sorted(ids, reverse=True)

    page1 = trade_service.list_trades(user_id=1, limit=2, offset=0)
    page2 = trade_service.list_trades(user_id=1, limit=2, offset=2)

    assert [t.id for t in page1.trades] == newest_first[:2]
    assert [t.id for t in page2.trades] == newest_first[2:]


def test_list_trades_orders_by_date_first_then_id(in_memory_db):
    """`trade_date desc` is the primary key of the order; `id desc` only
    breaks ties within a date. Asserting `id desc` alone would pass an
    implementation that had dropped the date ordering."""
    older = _create({"asset": "NQ", "trade_date": "2026-01-01"}).id
    newer_a = _create({"asset": "NQ", "trade_date": "2026-01-09"}).id
    newer_b = _create({"asset": "NQ", "trade_date": "2026-01-09", "pnl": 1.0}).id

    page = trade_service.list_trades(user_id=1)

    assert [t.id for t in page.trades] == [
        max(newer_a, newer_b),
        min(newer_a, newer_b),
        older,
    ]
