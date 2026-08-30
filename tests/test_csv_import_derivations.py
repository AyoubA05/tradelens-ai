"""CSV import must not have server-side derivations applied to it.

`create_trade` fills in `session`/`killzone` (from entry_time) and
`strategy_used` (from the owner's active Strategy Profile) for the live
create path. `csvio.import_trades_csv` is a third caller, and CSV_COLUMNS
carries neither `killzone` nor `entry_time` — so an unscoped derivation
stamps every imported row with a fabricated session/killzone, and any row
with a blank strategy_used with whichever profile the importer happens to
have active today. All three feed analytics (Journal session and strategy
filters, Overview's killzone panel, Analytics' by-strategy lens), and once
written there is no way to tell a derived value from a recorded one.

An imported trade that says nothing about these fields must keep NULL.
"""

from __future__ import annotations

import io

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import src.tradelens.services.app_settings as app_settings
import src.tradelens.services.csvio as csvio
import src.tradelens.services.strategy as strategy_service
import src.tradelens.services.trade_service as trade_service
from src.tradelens.db.models import Base, Trade, User


@pytest.fixture
def in_memory_db(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    TestSession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    for mod in (trade_service, app_settings, strategy_service):
        monkeypatch.setattr(mod, "SessionLocal", TestSession, raising=False)
    yield TestSession
    Base.metadata.drop_all(engine)


@pytest.fixture
def owner(in_memory_db):
    db = in_memory_db()
    alice = User(username="alice", password_hash="hash")
    db.add(alice)
    db.commit()
    db.refresh(alice)
    db.close()
    return alice.id


_CSV = (
    "trade_date,asset,direction,result,pnl,strategy_used\n"
    "2026-01-15,NQ,Long,Win,120.0,\n"
)


def _import(csv_text, owner_id):
    return csvio.import_trades_csv(io.BytesIO(csv_text.encode("utf-8")), owner_id)


def _only_trade(session_factory, owner_id):
    db = session_factory()
    try:
        return db.query(Trade).filter(Trade.user_id == owner_id).one()
    finally:
        db.close()


def test_csv_import_leaves_session_and_killzone_null(in_memory_db, owner):
    app_settings.set_timezone(owner, "America/New_York")

    inserted, _, errors = _import(_CSV, owner)

    assert (inserted, errors) == (1, [])
    trade = _only_trade(in_memory_db, owner)
    assert trade.session is None
    assert trade.killzone is None


def test_csv_import_does_not_stamp_the_active_strategy_profile(in_memory_db, owner):
    """A historical trade was not taken under whatever profile is active now."""
    strategy_service.upsert_strategy_profile(owner, name="ICT OB Continuation")

    inserted, _, errors = _import(_CSV, owner)

    assert (inserted, errors) == (1, [])
    assert _only_trade(in_memory_db, owner).strategy_used is None


def test_csv_import_keeps_the_strategy_the_row_actually_records(in_memory_db, owner):
    strategy_service.upsert_strategy_profile(owner, name="ICT OB Continuation")
    csv_text = (
        "trade_date,asset,direction,result,pnl,strategy_used\n"
        "2026-01-15,NQ,Long,Win,120.0,Asian Range Reversal\n"
    )

    inserted, _, errors = _import(csv_text, owner)

    assert (inserted, errors) == (1, [])
    assert _only_trade(in_memory_db, owner).strategy_used == "Asian Range Reversal"
