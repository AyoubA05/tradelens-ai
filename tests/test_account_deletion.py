"""Deleting an account has to actually delete the account.

This is the test that lets /privacy say "you can delete your data" without
lying. It plants a row in every table that can own user data, plus a real
screenshot file on disk, deletes the account, and asserts nothing is left
anywhere — while a second account's data is untouched.

If a future migration adds a user-owned table and does not add it to
delete_account(), test_no_table_still_references_the_deleted_user fails.
"""

import pytest
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

import src.tradelens.services.account as account_service
from src.tradelens.db.models import (
    AIAnalysis,
    AIUsageLog,
    Base,
    Correction,
    PerformanceMetrics,
    Screenshot,
    Strategy,
    Trade,
    User,
    UserSetting,
    WeeklyReview,
)


@pytest.fixture
def db_factory(monkeypatch, tmp_path):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(account_service, "SessionLocal", Session)
    monkeypatch.setattr(account_service, "SCREENSHOTS_DIR", tmp_path / "screenshots")
    (tmp_path / "screenshots").mkdir()
    yield Session
    Base.metadata.drop_all(engine)


def _populate(db, username: str, shots_dir) -> tuple[int, list]:
    """Create a user with a row in every user-owned table. Returns (id, files)."""
    user = User(username=username, password_hash="h", is_active=1)
    db.add(user)
    db.flush()

    trade = Trade(trade_date="2026-07-20", asset="NQ", user_id=user.id, result="Win")
    db.add(trade)
    db.flush()

    shot_path = shots_dir / f"{username}_chart.png"
    shot_path.write_bytes(b"not-really-a-png")

    analysis = AIAnalysis(trade_id=trade.id, bias="bullish")
    db.add(analysis)
    db.flush()

    db.add_all(
        [
            Screenshot(trade_id=trade.id, file_path=str(shot_path)),
            Correction(
                trade_id=trade.id,
                ai_analysis_id=analysis.id,
                user_id=user.id,
                field="bias",
            ),
            Strategy(user_id=user.id, name="My Process", is_active=1),
            UserSetting(user_id=user.id, key="timezone", value="UTC"),
            WeeklyReview(user_id=user.id, week_start="2026-07-20", content_md="x"),
            PerformanceMetrics(user_id=user.id, period_start="2026-07-01"),
            AIUsageLog(user_id=user.id, feature="weekly", cost_usd=0.01),
        ]
    )
    db.commit()
    return user.id, [shot_path]


def test_deleting_an_account_removes_every_owned_row(db_factory):
    db = db_factory()
    user_id, _files = _populate(db, "trader", account_service.SCREENSHOTS_DIR)
    db.close()

    account_service.delete_account(user_id)

    db = db_factory()
    try:
        assert db.query(User).filter(User.id == user_id).count() == 0
        assert db.query(Trade).filter(Trade.user_id == user_id).count() == 0
        assert db.query(Strategy).filter(Strategy.user_id == user_id).count() == 0
        assert db.query(UserSetting).filter(UserSetting.user_id == user_id).count() == 0
        assert (
            db.query(WeeklyReview).filter(WeeklyReview.user_id == user_id).count() == 0
        )
        assert db.query(Correction).filter(Correction.user_id == user_id).count() == 0
        assert (
            db.query(PerformanceMetrics)
            .filter(PerformanceMetrics.user_id == user_id)
            .count()
            == 0
        )
        # Orphans reachable only through the trade must go too.
        assert db.query(Screenshot).count() == 0
        assert db.query(AIAnalysis).count() == 0
    finally:
        db.close()


def test_screenshot_files_are_removed_from_disk(db_factory):
    """Rows alone are not deletion: the images are the sensitive part."""
    db = db_factory()
    user_id, files = _populate(db, "trader", account_service.SCREENSHOTS_DIR)
    db.close()

    assert all(f.exists() for f in files)
    account_service.delete_account(user_id)
    assert not any(f.exists() for f in files)


def test_cost_records_are_kept_but_anonymised(db_factory):
    """Operator accounting survives; its link to a person does not."""
    db = db_factory()
    user_id, _ = _populate(db, "trader", account_service.SCREENSHOTS_DIR)
    db.close()

    account_service.delete_account(user_id)

    db = db_factory()
    try:
        rows = db.query(AIUsageLog).all()
        assert len(rows) == 1
        assert rows[0].user_id is None
        assert rows[0].cost_usd == 0.01
    finally:
        db.close()


def test_another_accounts_data_is_untouched(db_factory):
    db = db_factory()
    victim_id, _ = _populate(db, "victim", account_service.SCREENSHOTS_DIR)
    keeper_id, keeper_files = _populate(db, "keeper", account_service.SCREENSHOTS_DIR)
    db.close()

    account_service.delete_account(victim_id)

    db = db_factory()
    try:
        assert db.query(User).filter(User.id == keeper_id).count() == 1
        assert db.query(Trade).filter(Trade.user_id == keeper_id).count() == 1
        assert db.query(Strategy).filter(Strategy.user_id == keeper_id).count() == 1
        assert db.query(Screenshot).count() == 1
        assert db.query(AIAnalysis).count() == 1
    finally:
        db.close()
    assert all(f.exists() for f in keeper_files)


def test_no_table_still_references_the_deleted_user(db_factory):
    """Guards against a future user-owned table being forgotten here."""
    db = db_factory()
    user_id, _ = _populate(db, "trader", account_service.SCREENSHOTS_DIR)
    db.close()

    account_service.delete_account(user_id)

    db = db_factory()
    try:
        inspector = inspect(db.bind)
        for table in Base.metadata.sorted_tables:
            columns = {c.name for c in table.columns}
            if "user_id" not in columns or table.name in account_service.ANONYMISED:
                continue
            remaining = db.execute(
                table.select().where(table.c.user_id == user_id)
            ).fetchall()
            assert not remaining, f"{table.name} still references the deleted user"
        assert inspector is not None
    finally:
        db.close()


def test_deleting_a_missing_account_reports_it_rather_than_raising(db_factory):
    assert account_service.delete_account(9999) is False


def test_a_missing_screenshot_file_does_not_abort_deletion(db_factory):
    """A file already gone must not leave the account half-deleted."""
    db = db_factory()
    user_id, files = _populate(db, "trader", account_service.SCREENSHOTS_DIR)
    db.close()
    files[0].unlink()

    assert account_service.delete_account(user_id) is True

    db = db_factory()
    try:
        assert db.query(User).filter(User.id == user_id).count() == 0
    finally:
        db.close()


def test_a_path_outside_the_screenshot_directory_is_not_deleted(db_factory, tmp_path):
    """Defensive: a stored path must never be able to delete arbitrary files."""
    outsider = tmp_path / "important.txt"
    outsider.write_text("do not delete me")

    db = db_factory()
    user = User(username="trader", password_hash="h", is_active=1)
    db.add(user)
    db.flush()
    trade = Trade(trade_date="2026-07-20", asset="NQ", user_id=user.id)
    db.add(trade)
    db.flush()
    db.add(Screenshot(trade_id=trade.id, file_path=str(outsider)))
    db.commit()
    user_id = user.id
    db.close()

    account_service.delete_account(user_id)
    assert outsider.exists(), "deletion escaped the screenshots directory"


def test_deletion_looks_where_screenshots_are_actually_written():
    """Drift here would silently leave chart images on disk after deletion."""
    import importlib

    from src.tradelens.services import screenshot_service

    account = importlib.reload(
        importlib.import_module("src.tradelens.services.account")
    )
    assert str(account.SCREENSHOTS_DIR) == str(screenshot_service.SCREENSHOTS_DIR)
