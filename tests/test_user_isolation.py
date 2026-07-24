from pathlib import Path

import pandas as pd
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

import src.tradelens.services.trade_service as trade_service
from src.tradelens.db.models import (
    AIAnalysis,
    Base,
    Correction,
    Screenshot,
    Trade,
    User,
)
from src.tradelens.services.trade_service import (
    create_trade,
    delete_trade,
    get_trade,
    get_trades,
    update_trade,
)

ROOT = Path(__file__).resolve().parents[1]


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


def _add_trade_dependents(session_factory, trade_id, user_id, marker):
    db = session_factory()
    screenshot = Screenshot(trade_id=trade_id, file_path=f"/tmp/{marker}.png")
    analysis = AIAnalysis(
        trade_id=trade_id,
        raw_response_json=f"{marker}-private-analysis",
        cost_usd=0.25,
    )
    db.add_all([screenshot, analysis])
    db.flush()
    correction = Correction(
        trade_id=trade_id,
        ai_analysis_id=analysis.id,
        field="bias",
        user_id=user_id,
    )
    db.add(correction)
    db.commit()
    ids = {
        "screenshot": screenshot.id,
        "analysis": analysis.id,
        "correction": correction.id,
    }
    db.close()
    return ids


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


def test_bulk_delete_removes_only_owner_trades_and_preserves_other_dependents(
    two_user_trades,
):
    user_a, user_b, trade_a = two_user_trades
    trade_b = create_trade(
        {"asset": "YM", "trade_date": "2026-07-02", "user_id": user_b.id}
    )
    second_trade_a = create_trade(
        {"asset": "ES", "trade_date": "2026-07-03", "user_id": user_a.id}
    )

    owner_dependents = _add_trade_dependents(
        trade_service.SessionLocal, second_trade_a.id, user_a.id, "alice"
    )
    foreign_dependents = _add_trade_dependents(
        trade_service.SessionLocal, trade_b.id, user_b.id, "bob"
    )

    deleted = trade_service.delete_all_trades(user_a.id)

    assert deleted == 2
    db = trade_service.SessionLocal()
    assert db.get(Trade, trade_a.id) is None
    assert db.get(Trade, second_trade_a.id) is None
    assert db.get(Trade, trade_b.id) is not None
    assert db.get(Screenshot, owner_dependents["screenshot"]) is None
    assert db.get(AIAnalysis, owner_dependents["analysis"]) is None
    assert db.get(Correction, owner_dependents["correction"]) is None
    assert db.get(Screenshot, foreign_dependents["screenshot"]) is not None
    assert db.get(AIAnalysis, foreign_dependents["analysis"]) is not None
    assert db.get(Correction, foreign_dependents["correction"]) is not None
    db.close()


def test_bulk_delete_prevents_private_children_attaching_to_reused_trade_id(
    two_user_trades,
):
    user_a, user_b, _ = two_user_trades
    existing_trade_b = create_trade(
        {"asset": "YM", "trade_date": "2026-07-02", "user_id": user_b.id}
    )
    private_trade_a = create_trade(
        {"asset": "ES", "trade_date": "2026-07-03", "user_id": user_a.id}
    )
    private_dependents = _add_trade_dependents(
        trade_service.SessionLocal, private_trade_a.id, user_a.id, "alice-reused"
    )

    assert private_trade_a.id > existing_trade_b.id
    assert trade_service.delete_all_trades(user_a.id) == 2

    replacement_trade_b = create_trade(
        {"asset": "RTY", "trade_date": "2026-07-04", "user_id": user_b.id}
    )
    assert replacement_trade_b.id == private_trade_a.id

    reread = get_trade(replacement_trade_b.id, user_id=user_b.id)
    assert reread.screenshots == []
    assert reread.ai_analysis is None

    db = trade_service.SessionLocal()
    assert db.get(Screenshot, private_dependents["screenshot"]) is None
    assert db.get(AIAnalysis, private_dependents["analysis"]) is None
    assert db.get(Correction, private_dependents["correction"]) is None
    db.close()


def test_bulk_delete_rolls_back_all_rows_after_dependent_delete_failure(
    two_user_trades,
):
    user_a, _, trade_a = two_user_trades
    dependent_ids = _add_trade_dependents(
        trade_service.SessionLocal, trade_a.id, user_a.id, "alice-rollback"
    )

    db = trade_service.SessionLocal()
    db.execute(
        text(
            """
            CREATE TRIGGER fail_analysis_delete
            BEFORE DELETE ON aianalysis
            WHEN NOT EXISTS (
                SELECT 1
                FROM corrections
                WHERE ai_analysis_id = OLD.id
            )
            BEGIN
                SELECT RAISE(FAIL, 'injected failure after correction delete');
            END
            """
        )
    )
    db.commit()
    db.close()

    with pytest.raises(Exception, match="injected failure after correction delete"):
        trade_service.delete_all_trades(user_a.id)

    db = trade_service.SessionLocal()
    assert db.get(Trade, trade_a.id) is not None
    assert db.get(Screenshot, dependent_ids["screenshot"]) is not None
    assert db.get(AIAnalysis, dependent_ids["analysis"]) is not None
    assert db.get(Correction, dependent_ids["correction"]) is not None
    db.close()


@pytest.mark.parametrize("invalid_user_id", [None, 0, -1, True, "1"])
def test_bulk_delete_rejects_invalid_owner_before_opening_session(
    monkeypatch, invalid_user_id
):
    session_calls = 0

    def session_never_called():
        nonlocal session_calls
        session_calls += 1
        raise AssertionError("invalid owners must not construct a database session")

    monkeypatch.setattr(trade_service, "SessionLocal", session_never_called)

    with pytest.raises(ValueError, match="user_id must be a positive integer"):
        trade_service.delete_all_trades(invalid_user_id)

    assert session_calls == 0


def test_ownerless_settings_page_disables_bulk_delete(monkeypatch):
    from streamlit.testing.v1 import AppTest

    from src.tradelens.services import cost

    monkeypatch.setattr(
        cost,
        "monthly_cost_by_feature",
        lambda *_args, **_kwargs: pd.DataFrame(
            columns=["feature", "cost_usd", "calls"]
        ),
    )

    at = AppTest.from_file(
        str(ROOT / "src" / "tradelens" / "ui" / "pages" / "9_Settings.py"),
        default_timeout=30,
    )
    at.session_state["authenticated"] = True
    at.run()
    at.text_input(key="danger_confirm").set_value("DELETE").run()

    assert not at.exception
    buttons = [button for button in at.button if button.label == "Delete ALL trades"]
    assert len(buttons) == 1
    assert buttons[0].disabled
