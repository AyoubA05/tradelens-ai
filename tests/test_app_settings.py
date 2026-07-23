"""User-scoped persistent application settings."""

import importlib
from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import src.tradelens.services.app_settings as app_settings
from src.tradelens.db.models import Base, User, UserSetting


@pytest.fixture()
def in_memory_db(monkeypatch):
    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine)
    test_session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(app_settings, "SessionLocal", test_session, raising=False)
    return test_session


@pytest.fixture()
def two_users(in_memory_db):
    db = in_memory_db()
    alice = User(username="alice", password_hash="hash")
    bob = User(username="bob", password_hash="hash")
    db.add_all([alice, bob])
    db.commit()
    db.refresh(alice)
    db.refresh(bob)
    db.close()
    return alice, bob


def test_timezones_are_user_scoped(in_memory_db, two_users):
    alice, bob = two_users

    app_settings.set_timezone(alice.id, "America/New_York")
    app_settings.set_timezone(bob.id, "Europe/London")

    assert app_settings.get_timezone(alice.id) == "America/New_York"
    assert app_settings.get_timezone(bob.id) == "Europe/London"


def test_timezone_defaults_when_unset(in_memory_db, two_users):
    alice, _ = two_users

    assert app_settings.get_timezone(alice.id) == app_settings.DEFAULT_TIMEZONE


def test_set_timezone_empty_value_uses_default(in_memory_db, two_users):
    alice, _ = two_users

    app_settings.set_timezone(alice.id, "")

    assert app_settings.get_timezone(alice.id) == app_settings.DEFAULT_TIMEZONE


def test_other_settings_roundtrip_and_update_timestamp(in_memory_db, two_users):
    alice, _ = two_users

    app_settings.set_setting(alice.id, "dashboard_layout", "compact")
    app_settings.set_setting(alice.id, "date_format", "YYYY-MM-DD")
    app_settings.set_setting(alice.id, "dashboard_layout", "expanded")

    assert app_settings.get_setting(alice.id, "dashboard_layout") == "expanded"
    assert app_settings.get_setting(alice.id, "date_format") == "YYYY-MM-DD"
    assert app_settings.get_setting(alice.id, "missing", "fallback") == "fallback"

    db = in_memory_db()
    rows = db.query(UserSetting).all()
    db.close()
    assert len(rows) == 2
    rows_by_key = {row.key: row for row in rows}
    assert set(rows_by_key) == {"dashboard_layout", "date_format"}
    assert rows_by_key["dashboard_layout"].user_id == alice.id
    assert rows_by_key["dashboard_layout"].value == "expanded"
    assert rows_by_key["date_format"].value == "YYYY-MM-DD"
    assert (
        datetime.fromisoformat(rows_by_key["dashboard_layout"].updated_at)
        .utcoffset()
        .total_seconds()
        == 0
    )


@pytest.mark.parametrize("invalid_user_id", [None, 0, -1, True, "1"])
def test_setting_operations_reject_invalid_owner_without_touching_rows(
    in_memory_db, two_users, invalid_user_id
):
    alice, _ = two_users
    app_settings.set_timezone(alice.id, "Europe/London")

    operations = (
        lambda: app_settings.get_setting(invalid_user_id, "trading_timezone"),
        lambda: app_settings.set_setting(invalid_user_id, "trading_timezone", "UTC"),
        lambda: app_settings.get_timezone(invalid_user_id),
        lambda: app_settings.set_timezone(invalid_user_id, "UTC"),
    )
    for operation in operations:
        with pytest.raises(ValueError, match="user_id must be a positive integer"):
            operation()

    db = in_memory_db()
    rows = db.query(UserSetting).all()
    db.close()
    assert len(rows) == 1
    assert rows[0].user_id == alice.id
    assert rows[0].value == "Europe/London"


def test_module_import_is_streamlit_free():
    mod = importlib.reload(app_settings)
    assert hasattr(mod, "get_timezone")
