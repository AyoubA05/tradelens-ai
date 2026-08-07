"""User-scoped persistent application settings."""

import importlib
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker

import src.tradelens.services.app_settings as app_settings
from src.tradelens.db.models import Base, User, UserSetting

ROOT = Path(__file__).resolve().parents[1]


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


def test_other_settings_roundtrip_updates_timestamp_and_preserves_sibling_key(
    in_memory_db, two_users, monkeypatch
):
    alice, _ = two_users
    timestamps = iter(
        (
            datetime(2026, 7, 22, 12, 0, tzinfo=timezone.utc),
            datetime(2026, 7, 22, 12, 1, tzinfo=timezone.utc),
            datetime(2026, 7, 22, 12, 2, tzinfo=timezone.utc),
        )
    )

    class ControlledClock:
        @classmethod
        def now(cls, tz):
            assert tz is timezone.utc
            return next(timestamps)

    monkeypatch.setattr(app_settings, "datetime", ControlledClock)

    app_settings.set_setting(alice.id, "dashboard_layout", "compact")
    db = in_memory_db()
    inserted_timestamp = (
        db.query(UserSetting)
        .filter(UserSetting.user_id == alice.id, UserSetting.key == "dashboard_layout")
        .one()
        .updated_at
    )
    db.close()

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
    updated_timestamp = rows_by_key["dashboard_layout"].updated_at
    assert inserted_timestamp != updated_timestamp
    for value in (inserted_timestamp, updated_timestamp):
        assert datetime.fromisoformat(value).utcoffset().total_seconds() == 0


@pytest.mark.parametrize("invalid_user_id", [None, 0, -1, True, "1"])
def test_setting_operations_reject_invalid_owner_without_touching_rows(
    in_memory_db, two_users, invalid_user_id, monkeypatch
):
    alice, _ = two_users
    app_settings.set_timezone(alice.id, "Europe/London")
    session_calls = 0

    def session_never_called():
        nonlocal session_calls
        session_calls += 1
        raise AssertionError("invalid owners must not construct a database session")

    monkeypatch.setattr(app_settings, "SessionLocal", session_never_called)

    operations = (
        lambda: app_settings.get_setting(invalid_user_id, "trading_timezone"),
        lambda: app_settings.set_setting(invalid_user_id, "trading_timezone", "UTC"),
        lambda: app_settings.get_timezone(invalid_user_id),
        lambda: app_settings.set_timezone(invalid_user_id, "UTC"),
    )
    for operation in operations:
        with pytest.raises(ValueError, match="user_id must be a positive integer"):
            operation()

    assert session_calls == 0

    db = in_memory_db()
    rows = db.query(UserSetting).all()
    db.close()
    assert len(rows) == 1
    assert rows[0].user_id == alice.id
    assert rows[0].value == "Europe/London"


def test_set_setting_recovers_when_a_concurrent_insert_wins(monkeypatch, tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'settings.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    test_session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(app_settings, "SessionLocal", test_session)

    db = test_session()
    alice = User(username="alice", password_hash="hash")
    db.add(alice)
    db.commit()
    db.refresh(alice)
    user_id = alice.id
    db.close()

    collision_injected = False

    def insert_competing_row(session, _flush_context, _instances):
        nonlocal collision_injected
        if collision_injected:
            return
        if not any(
            isinstance(row, UserSetting)
            and row.user_id == user_id
            and row.key == "trading_timezone"
            for row in session.new
        ):
            return

        collision_injected = True
        competitor = test_session()
        try:
            competitor.add(
                UserSetting(
                    user_id=user_id,
                    key="trading_timezone",
                    value="Europe/London",
                    updated_at="2026-07-22T12:00:00+00:00",
                )
            )
            competitor.commit()
        finally:
            competitor.close()

    event.listen(test_session.class_, "before_flush", insert_competing_row)
    try:
        app_settings.set_setting(user_id, "trading_timezone", "America/Chicago")
    finally:
        event.remove(test_session.class_, "before_flush", insert_competing_row)

    db = test_session()
    rows = db.query(UserSetting).all()
    db.close()
    assert collision_injected is True
    assert len(rows) == 1
    assert rows[0].user_id == user_id
    assert rows[0].key == "trading_timezone"
    assert rows[0].value == "America/Chicago"


@pytest.mark.parametrize("page", ["1_NewTrade.py", "9_Settings.py"])
def test_ownerless_pages_do_not_call_or_persist_settings(monkeypatch, page):
    from streamlit.testing.v1 import AppTest

    from src.tradelens.services import sample_data, trade_service

    service_calls = []

    def settings_service_called(*_args, **_kwargs):
        service_calls.append(page)
        raise AssertionError("ownerless page must not call the settings service")

    def file_write_attempted(*_args, **_kwargs):
        raise AssertionError("ownerless page must not write a global settings file")

    monkeypatch.setattr(app_settings, "get_timezone", settings_service_called)
    monkeypatch.setattr(app_settings, "set_timezone", settings_service_called)
    monkeypatch.setattr(Path, "write_text", file_write_attempted)
    monkeypatch.setattr(trade_service, "get_trades", lambda **_kwargs: [])
    monkeypatch.setattr(sample_data, "count_sample_trades", lambda _user_id: 0)

    at = AppTest.from_file(
        str(ROOT / "src" / "tradelens" / "ui" / "pages" / page),
        default_timeout=30,
    )
    at.session_state["authenticated"] = True
    at.run()

    assert not at.exception
    assert service_calls == []


def test_module_import_is_streamlit_free():
    mod = importlib.reload(app_settings)
    assert hasattr(mod, "get_timezone")


# ---------------------------------------------------------------------------
# Task 13 — the Danger Zone perimeter, and where red is allowed to appear.
# ---------------------------------------------------------------------------

_SETTINGS_PAGE = (
    Path(__file__).resolve().parents[1] / "src/tradelens/ui/pages/9_Settings.py"
)


def _src() -> str:
    return _SETTINGS_PAGE.read_text(encoding="utf-8")


def test_the_danger_zone_is_one_contained_perimeter():
    """Spec §6.7: one contained perimeter around both disclosures, their
    confirmation fields, and their destructive buttons — drawn with
    TL_LINE_STRONG.

    The plan's version of this test looked for `--tl-line-strong` inside a CSS
    block containing the string "tl-danger-zone". The perimeter is not on that
    class: it is on the KEYED CONTAINER, `.st-key-tl_danger_zone`, spelled
    with underscores, because the expanders and buttons inside it are
    Streamlit's own elements and only the container encloses them all. So the
    plan's test failed while a perimeter was present, and would have kept
    failing after any correct fix. It reads the real selector now.
    """
    from src.tradelens.ui import design_system as ds

    css = ds.build_css()
    marker = ".st-key-tl_danger_zone {"
    assert marker in css, "no perimeter on the danger-zone container"
    block = css[css.index(marker) : css.index("}", css.index(marker))]
    assert "border:" in block
    assert "var(--tl-line-strong)" in block, block
    assert "var(--tl-danger)" not in block, (
        "the perimeter is spending the danger hue that the heading and the "
        "destructive buttons need"
    )


def test_red_inside_settings_is_confined_to_destructive_things():
    """Red is reserved for the Danger Zone and destructive actions; warnings
    are amber or neutral.

    The plan proposed `assert "TL_DANGER" not in outside(source, "danger_zone")`
    on the page source. That is vacuous twice over: there is no function named
    `danger_zone`, so `outside()` returns the whole file, and the page never
    names `TL_DANGER` at all — its colour comes from CSS classes. It passed
    with the assertion doing nothing. The property is checked where the colour
    actually lives.
    """
    from src.tradelens.ui import design_system as ds

    css = ds.build_css()
    allowed = ("danger", "error", "fail", "negative", "leak", "pnl-neg")
    offenders = []
    for block in css.split("}"):
        if "var(--tl-danger)" not in block:
            continue
        selector = block.split("{")[0]
        if "st-key-tl_settings" in selector or "tl-setting" in selector:
            if not any(word in selector for word in allowed):
                offenders.append(selector.strip()[:80])
    assert not offenders, f"red on a non-destructive Settings surface: {offenders}"


def test_both_destructive_gates_still_require_their_exact_phrase():
    """Preserved, not redesigned: the typed confirmation is the last thing
    between a trader and an irreversible action."""
    src = _src()
    assert 'st.text_input(\n            "Type DELETE to confirm"' in src or (
        "Type DELETE to confirm" in src
    )
    assert "Type DELETE MY ACCOUNT to confirm" in src
    assert 'typed != "DELETE"' in src
    assert '_confirm_account.strip() != "DELETE MY ACCOUNT"' in src


def test_settings_stays_the_quietest_destination():
    """Spec §6.7: no chart, no promotional banner, no bright primary CTA."""
    src = _src()
    assert 'type="primary"' not in src
    assert "plotly_chart" not in src
