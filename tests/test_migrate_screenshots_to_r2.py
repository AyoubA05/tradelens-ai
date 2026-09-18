"""Legacy local screenshots move to R2: object first, row second, never another owner's file."""

import pathlib

import pytest

from scripts import migrate_screenshots_to_r2 as mig
from src.tradelens.api import storage
from src.tradelens.db.models import Screenshot, Trade
from src.tradelens.db.session import SessionLocal
from src.tradelens.services import screenshot_service

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


class FakeR2:
    """An in-memory stand-in for the R2 client. No network, ever."""

    def __init__(self, fail_put=False, lie_about_size=False):
        self.objects = {}
        self.fail_put = fail_put
        self.lie_about_size = lie_about_size

    def put_object(self, Bucket, Key, Body, ContentType):
        if self.fail_put:
            raise RuntimeError("store down")
        self.objects[Key] = (Body, ContentType)

    def head_object(self, Bucket, Key):
        if Key not in self.objects:
            raise RuntimeError("missing")
        length = len(self.objects[Key][0])
        return {"ContentLength": 1 if self.lie_about_size else length}


def _trade(owner):
    db = SessionLocal()
    try:
        row = Trade(user_id=owner, asset="NQ", direction="Long", result="Win")
        db.add(row)
        db.commit()
        return row.id
    finally:
        db.close()


def _shot(trade_id, path):
    db = SessionLocal()
    try:
        row = Screenshot(trade_id=trade_id, file_path=str(path))
        db.add(row)
        db.commit()
        return row.id
    finally:
        db.close()


def _path_of(shot_id):
    db = SessionLocal()
    try:
        return db.get(Screenshot, shot_id).file_path
    finally:
        db.close()


@pytest.fixture
def store(monkeypatch, tmp_path):
    root = tmp_path / "screenshots"
    root.mkdir()
    monkeypatch.setattr(screenshot_service, "SCREENSHOTS_DIR", root)
    fake = FakeR2()
    monkeypatch.setattr(storage, "_client", lambda: fake)
    monkeypatch.setattr(storage, "r2_config", lambda: {"bucket": "b"})
    return root, fake


def _legacy_png(root, trade, name="chart"):
    file = root / ("%d_%s.png" % (trade, name))
    file.write_bytes(PNG)
    return file


def test_dry_run_changes_nothing(two_users, store):
    root, fake = store
    owner, _ = two_users
    trade = _trade(owner)
    file = _legacy_png(root, trade)
    shot = _shot(trade, file)
    report = mig.migrate_owner(owner, apply=False)
    assert report.migrated == [shot]
    assert fake.objects == {}
    assert _path_of(shot) == str(file)


def test_apply_uploads_then_rewrites_the_row(two_users, store):
    root, fake = store
    owner, _ = two_users
    trade = _trade(owner)
    file = _legacy_png(root, trade)
    shot = _shot(trade, file)
    report = mig.migrate_owner(owner, apply=True)
    assert report.migrated == [shot] and report.failed == []
    key = _path_of(shot)
    assert key in fake.objects and fake.objects[key] == (PNG, "image/png")
    assert storage._is_final_key(key, owner, trade)
    # The legacy bytes are never destroyed by this script.
    assert file.exists() and file.read_bytes() == PNG
    # Idempotent: a second run sees a row that already names this owner's object.
    again = mig.migrate_owner(owner, apply=True)
    assert again.migrated == [] and again.skipped == [] and again.failed == []
    assert _path_of(shot) == key


def test_a_failed_upload_leaves_the_row_untouched(two_users, store, monkeypatch):
    root, _ = store
    owner, _ = two_users
    monkeypatch.setattr(storage, "_client", lambda: FakeR2(fail_put=True))
    trade = _trade(owner)
    file = _legacy_png(root, trade)
    shot = _shot(trade, file)
    report = mig.migrate_owner(owner, apply=True)
    assert report.failed == [shot] and report.migrated == []
    assert _path_of(shot) == str(file)
    assert file.exists()


def test_a_failed_verification_leaves_the_row_untouched(two_users, store, monkeypatch):
    """The object exists but does not hold our bytes — the reference stays legacy."""
    root, _ = store
    owner, _ = two_users
    monkeypatch.setattr(storage, "_client", lambda: FakeR2(lie_about_size=True))
    trade = _trade(owner)
    file = _legacy_png(root, trade)
    shot = _shot(trade, file)
    report = mig.migrate_owner(owner, apply=True)
    assert report.failed == [shot] and report.migrated == []
    assert _path_of(shot) == str(file)


def test_another_owners_file_and_escapes_are_never_uploaded(two_users, store, tmp_path):
    root, fake = store
    owner, other = two_users
    theirs = _trade(other)
    their_file = _legacy_png(root, theirs, name="theirs")
    mine = _trade(owner)
    wrong_name = _shot(mine, their_file)  # names another trade's file

    # Correctly named, but not inside the screenshots root.
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    stray = elsewhere / ("%d_chart.png" % mine)
    stray.write_bytes(PNG)
    absolute_escape = _shot(mine, stray)
    traversal = _shot(mine, root / ".." / "elsewhere" / ("%d_chart.png" % mine))
    link = root / ("%d_link.png" % mine)
    link.symlink_to(stray)
    symlinked = _shot(mine, link)

    outside = _shot(mine, pathlib.Path("/etc/passwd"))
    remote = _shot(mine, "https://example.test/chart.png")
    report = mig.migrate_owner(owner, apply=True)
    assert sorted(report.skipped) == sorted(
        [wrong_name, absolute_escape, traversal, symlinked, outside, remote]
    )
    assert report.migrated == [] and report.failed == []
    assert fake.objects == {}
    assert their_file.exists()


def test_a_missing_file_is_reported_not_raised(two_users, store):
    root, _ = store
    owner, _ = two_users
    trade = _trade(owner)
    shot = _shot(trade, root / ("%d_gone.png" % trade))
    report = mig.migrate_owner(owner, apply=True)
    assert report.missing == [shot]
    assert report.failed == [] and report.migrated == []


def test_a_non_image_is_skipped(two_users, store):
    root, fake = store
    owner, _ = two_users
    trade = _trade(owner)
    file = root / ("%d_chart.png" % trade)
    file.write_bytes(b"#!/bin/sh\n")
    shot = _shot(trade, file)
    assert mig.migrate_owner(owner, apply=True).skipped == [shot]
    assert fake.objects == {}
