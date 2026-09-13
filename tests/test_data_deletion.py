"""Bulk and account deletion erase objects before the rows that name them.

The rule these tests hold the services to (Phase 9, owner-designated blocking
work): no path may report a successful deletion while an owned private object
that should have been removed failed cleanup. A blocked cleanup deletes no row
and says how much was left behind, and whether a retry can help.
"""

from __future__ import annotations

import datetime as dt
import os

from src.tradelens.api.storage import ObjectCleanup
from src.tradelens.db.models import Screenshot, Trade, TradeSummaryResult, User
from src.tradelens.db.session import SessionLocal
from src.tradelens.services import data_deletion


def _trade(owner, file_path=None):
    db = SessionLocal()
    try:
        row = Trade(user_id=owner, asset="NQ", direction="Long", result="Win")
        db.add(row)
        db.commit()
        if file_path is not None:
            db.add(Screenshot(trade_id=row.id, file_path=file_path))
            db.commit()
        return row.id
    finally:
        db.close()


def _count(model, **where):
    db = SessionLocal()
    try:
        query = db.query(model)
        for key, value in where.items():
            query = query.filter(getattr(model, key) == value)
        return query.count()
    finally:
        db.close()


def _add_shot(trade_id, file_path):
    db = SessionLocal()
    try:
        db.add(Screenshot(trade_id=trade_id, file_path=file_path))
        db.commit()
    finally:
        db.close()


def _paths(trade_id):
    db = SessionLocal()
    try:
        return [
            p
            for (p,) in db.query(Screenshot.file_path)
            .filter(Screenshot.trade_id == trade_id)
            .all()
        ]
    finally:
        db.close()


def _cleans_what_is_stored(record=None):
    """A fake cleanup that deletes exactly the keys stored for the trade now."""

    def cleanup(user_id, trade_id):
        keys = _paths(trade_id)
        if record is not None:
            record.append((trade_id, sorted(keys)))
        return ObjectCleanup(deleted=keys, failed=[], skipped=[])

    return cleanup


def _clean(user_id, trade_id):
    return ObjectCleanup(deleted=[], failed=[], skipped=[])


# ── objects before rows ───────────────────────────────────────────────────


def test_every_trades_objects_are_deleted_before_any_row(two_users, monkeypatch):
    owner = two_users[1]
    first = _trade(owner, "u/%d/t/1/a.png" % owner)
    second = _trade(owner, "u/%d/t/2/b.png" % owner)
    seen = []

    def cleanup(user_id, trade_id):
        # Every row must still exist while any object is being removed.
        seen.append((user_id, trade_id, _count(Trade, user_id=owner)))
        return ObjectCleanup(deleted=_paths(trade_id), failed=[], skipped=[])

    monkeypatch.setattr(data_deletion.storage, "delete_trade_objects", cleanup)
    outcome = data_deletion.delete_all_trades_and_objects(owner)
    assert outcome == data_deletion.DeletionOutcome(2, 0, 0, False)
    assert sorted(seen) == sorted([(owner, first, 2), (owner, second, 2)])
    assert _count(Trade, user_id=owner) == 0


def test_one_failed_object_deletes_no_row_and_is_retryable(two_users, monkeypatch):
    owner = two_users[1]
    _trade(owner, "u/%d/t/1/a.png" % owner)
    _trade(owner, "u/%d/t/2/b.png" % owner)
    results = iter(
        [
            ObjectCleanup(deleted=["k"], failed=[], skipped=[]),
            ObjectCleanup(deleted=[], failed=["k2"], skipped=[]),
        ]
    )
    monkeypatch.setattr(
        data_deletion.storage, "delete_trade_objects", lambda u, t: next(results)
    )
    outcome = data_deletion.delete_all_trades_and_objects(owner)
    assert outcome == data_deletion.DeletionOutcome(0, 1, 0, True)
    assert _count(Trade, user_id=owner) == 2


def test_remaining_and_unresolvable_are_counted_separately(two_users, monkeypatch):
    owner = two_users[1]
    _trade(owner, "u/%d/t/1/a.png" % owner)
    monkeypatch.setattr(
        data_deletion.storage,
        "delete_trade_objects",
        lambda u, t: ObjectCleanup(
            deleted=[], failed=["f1", "f2"], skipped=["/etc/passwd"]
        ),
    )
    outcome = data_deletion.delete_all_trades_and_objects(owner)
    assert (outcome.remaining, outcome.unresolvable, outcome.blocked) == (2, 1, True)


def test_a_key_outside_this_owners_prefix_blocks_as_unresolvable(
    two_users, monkeypatch
):
    first, owner = two_users
    _trade(owner, "u/%d/t/9/stolen.png" % first)
    monkeypatch.setattr(
        data_deletion.storage,
        "delete_trade_objects",
        lambda u, t: ObjectCleanup(
            deleted=[], failed=[], skipped=["u/%d/t/9/stolen.png" % first]
        ),
    )
    outcome = data_deletion.delete_all_trades_and_objects(owner)
    assert outcome == data_deletion.DeletionOutcome(0, 0, 1, True)
    assert _count(Trade, user_id=owner) == 1


def test_bulk_deletion_never_touches_another_owners_trades(two_users, monkeypatch):
    first, owner = two_users
    theirs = _trade(first, "u/%d/t/1/theirs.png" % first)
    _trade(owner)
    calls = []

    def cleanup(user_id, trade_id):
        calls.append((user_id, trade_id))
        return ObjectCleanup(deleted=[], failed=[], skipped=[])

    monkeypatch.setattr(data_deletion.storage, "delete_trade_objects", cleanup)
    data_deletion.delete_all_trades_and_objects(owner)
    assert calls and all(u == owner for u, _t in calls)
    assert theirs not in [t for _u, t in calls]
    assert _count(Trade, id=theirs) == 1
    assert _count(Screenshot, trade_id=theirs) == 1


def test_an_owner_with_no_trades_deletes_nothing_and_is_not_blocked(
    two_users, monkeypatch
):
    owner = two_users[1]
    monkeypatch.setattr(data_deletion.storage, "delete_trade_objects", _clean)
    outcome = data_deletion.delete_all_trades_and_objects(owner)
    assert outcome == data_deletion.DeletionOutcome(0, 0, 0, False)


# ── S8: legacy local screenshots, confined to the approved root ───────────


def test_a_path_outside_the_root_is_never_deleted_and_blocks(
    two_users, monkeypatch, tmp_path
):
    owner = two_users[1]
    root = tmp_path / "screenshots"
    root.mkdir()
    outside = tmp_path / "precious.txt"
    outside.write_text("keep me")
    for key in (str(outside), str(root / ".." / "precious.txt")):
        _trade(owner, key)
    monkeypatch.setattr(data_deletion._account, "SCREENSHOTS_DIR", root)
    keys = iter([str(outside), str(root / ".." / "precious.txt")])
    monkeypatch.setattr(
        data_deletion.storage,
        "delete_trade_objects",
        lambda u, t: ObjectCleanup(deleted=[], failed=[], skipped=[next(keys)]),
    )
    outcome = data_deletion.delete_all_trades_and_objects(owner)
    assert outcome == data_deletion.DeletionOutcome(0, 0, 2, True)
    assert outside.read_text() == "keep me"
    assert _count(Trade, user_id=owner) == 2


def test_a_symlink_inside_the_root_pointing_outside_is_never_followed(
    two_users, monkeypatch, tmp_path
):
    owner = two_users[1]
    root = tmp_path / "screenshots"
    root.mkdir()
    target = tmp_path / "secret.txt"
    target.write_text("keep me")
    link = root / "innocent.png"
    os.symlink(target, link)
    _trade(owner, str(link))
    monkeypatch.setattr(data_deletion._account, "SCREENSHOTS_DIR", root)
    monkeypatch.setattr(
        data_deletion.storage,
        "delete_trade_objects",
        lambda u, t: ObjectCleanup(deleted=[], failed=[], skipped=[str(link)]),
    )
    outcome = data_deletion.delete_all_trades_and_objects(owner)
    assert outcome.blocked is True and outcome.unresolvable == 1
    assert target.read_text() == "keep me"


# ── S7: derived summaries go with the trades ──────────────────────────────


def test_delete_all_trades_also_removes_trade_summaries(two_users, monkeypatch):
    first, owner = two_users
    _trade(owner)
    db = SessionLocal()
    try:
        for user_id in (first, owner):
            db.add(
                TradeSummaryResult(
                    user_id=user_id,
                    summary_key="k%d" % user_id,
                    filters_json="{}",
                    content_md="A summary that quotes a trade note.",
                    reviewed_trades=1,
                    created_at=dt.datetime.now(dt.timezone.utc),
                )
            )
        db.commit()
    finally:
        db.close()
    monkeypatch.setattr(data_deletion.storage, "delete_trade_objects", _clean)
    data_deletion.delete_all_trades_and_objects(owner)
    assert _count(TradeSummaryResult, user_id=owner) == 0
    assert _count(TradeSummaryResult, user_id=first) == 1


def test_summaries_are_removed_even_when_no_trades_remain(two_users, monkeypatch):
    owner = two_users[1]
    db = SessionLocal()
    try:
        db.add(
            TradeSummaryResult(
                user_id=owner,
                summary_key="orphan",
                filters_json="{}",
                content_md="Left behind after the trades were deleted.",
                reviewed_trades=3,
                created_at=dt.datetime.now(dt.timezone.utc),
            )
        )
        db.commit()
    finally:
        db.close()
    monkeypatch.setattr(data_deletion.storage, "delete_trade_objects", _clean)
    outcome = data_deletion.delete_all_trades_and_objects(owner)
    assert outcome == data_deletion.DeletionOutcome(0, 0, 0, False)
    assert _count(TradeSummaryResult, user_id=owner) == 0


# ── account deletion ──────────────────────────────────────────────────────

# ── S8, as tightened by the Group A review ────────────────────────────────


def test_a_legacy_file_named_for_its_trade_is_removed_and_does_not_block(
    two_users, monkeypatch, tmp_path
):
    owner = two_users[1]
    root = tmp_path / "screenshots"
    root.mkdir()
    trade_id = _trade(owner)
    legacy = root / ("%d_old.png" % trade_id)
    legacy.write_bytes(b"png")
    _add_shot(trade_id, str(legacy))
    monkeypatch.setattr(data_deletion._account, "SCREENSHOTS_DIR", root)
    monkeypatch.setattr(
        data_deletion.storage,
        "delete_trade_objects",
        lambda u, t: ObjectCleanup(deleted=[], failed=[], skipped=_paths(t)),
    )
    outcome = data_deletion.delete_all_trades_and_objects(owner)
    assert outcome == data_deletion.DeletionOutcome(1, 0, 0, False)
    assert not legacy.exists()


def test_a_missing_legacy_file_named_for_its_trade_counts_as_already_gone(
    two_users, monkeypatch, tmp_path
):
    owner = two_users[1]
    root = tmp_path / "screenshots"
    root.mkdir()
    trade_id = _trade(owner)
    _add_shot(trade_id, str(root / ("%d_never-there.png" % trade_id)))
    monkeypatch.setattr(data_deletion._account, "SCREENSHOTS_DIR", root)
    monkeypatch.setattr(
        data_deletion.storage,
        "delete_trade_objects",
        lambda u, t: ObjectCleanup(deleted=[], failed=[], skipped=_paths(t)),
    )
    outcome = data_deletion.delete_all_trades_and_objects(owner)
    assert outcome == data_deletion.DeletionOutcome(1, 0, 0, False)


def test_another_trades_legacy_file_inside_the_root_is_never_deleted(
    two_users, monkeypatch, tmp_path
):
    """B2: the root alone is not ownership. A row naming another trade's legacy
    file — another tenant's — must not delete it, and must block."""
    first, owner = two_users
    root = tmp_path / "screenshots"
    root.mkdir()
    theirs = _trade(first)
    their_file = root / ("%d_their_chart.png" % theirs)
    their_file.write_bytes(b"theirs")
    mine = _trade(owner)
    _add_shot(mine, str(their_file))
    monkeypatch.setattr(data_deletion._account, "SCREENSHOTS_DIR", root)
    monkeypatch.setattr(
        data_deletion.storage,
        "delete_trade_objects",
        lambda u, t: ObjectCleanup(deleted=[], failed=[], skipped=_paths(t)),
    )
    outcome = data_deletion.delete_all_trades_and_objects(owner)
    assert outcome == data_deletion.DeletionOutcome(0, 0, 1, True)
    assert their_file.read_bytes() == b"theirs"
    assert _count(Trade, id=mine) == 1


def test_a_legacy_file_that_cannot_be_removed_blocks(two_users, monkeypatch, tmp_path):
    """N3: only a missing file counts as gone; a permission error does not."""
    owner = two_users[1]
    root = tmp_path / "screenshots"
    root.mkdir()
    trade_id = _trade(owner)
    stuck = root / ("%d_stuck.png" % trade_id)
    stuck.write_bytes(b"png")
    _add_shot(trade_id, str(stuck))
    monkeypatch.setattr(data_deletion._account, "SCREENSHOTS_DIR", root)
    monkeypatch.setattr(
        data_deletion.storage,
        "delete_trade_objects",
        lambda u, t: ObjectCleanup(deleted=[], failed=[], skipped=_paths(t)),
    )

    def refuse(self, *args, **kwargs):
        raise PermissionError("read-only volume")

    monkeypatch.setattr(type(stuck), "unlink", refuse)
    outcome = data_deletion.delete_all_trades_and_objects(owner)
    assert outcome == data_deletion.DeletionOutcome(0, 0, 1, True)
    assert _count(Trade, id=trade_id) == 1


def test_a_relative_legacy_path_resolves_from_the_project_not_the_cwd(
    two_users, monkeypatch, tmp_path
):
    """S1: the legacy writer stored "data/screenshots/…"; a process started in
    another directory must still find — and remove — the real file."""
    owner = two_users[1]
    project = tmp_path / "project"
    root = project / "data" / "screenshots"
    root.mkdir(parents=True)
    trade_id = _trade(owner)
    real = root / ("%d_chart.png" % trade_id)
    real.write_bytes(b"png")
    _add_shot(trade_id, "data/screenshots/%d_chart.png" % trade_id)
    monkeypatch.setattr(data_deletion._account, "SCREENSHOTS_DIR", root)
    monkeypatch.setattr(data_deletion._account, "_PROJECT_ROOT", project)
    elsewhere = tmp_path / "elsewhere"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)
    monkeypatch.setattr(
        data_deletion.storage,
        "delete_trade_objects",
        lambda u, t: ObjectCleanup(deleted=[], failed=[], skipped=_paths(t)),
    )
    outcome = data_deletion.delete_all_trades_and_objects(owner)
    assert outcome == data_deletion.DeletionOutcome(1, 0, 0, False)
    assert not real.exists()


def test_legacy_cleanup_is_idempotent_across_a_retry(two_users, monkeypatch, tmp_path):
    owner = two_users[1]
    root = tmp_path / "screenshots"
    root.mkdir()
    legacy_trade = _trade(owner)
    legacy = root / ("%d_old.png" % legacy_trade)
    legacy.write_bytes(b"png")
    _add_shot(legacy_trade, str(legacy))
    r2_trade = _trade(owner, "u/%d/t/2/b.png" % owner)
    monkeypatch.setattr(data_deletion._account, "SCREENSHOTS_DIR", root)
    attempts = {"n": 0}

    def cleanup(user_id, trade_id):
        if trade_id == r2_trade:
            attempts["n"] += 1
            failed = _paths(trade_id) if attempts["n"] == 1 else []
            deleted = [] if attempts["n"] == 1 else _paths(trade_id)
            return ObjectCleanup(deleted=deleted, failed=failed, skipped=[])
        return ObjectCleanup(deleted=[], failed=[], skipped=_paths(trade_id))

    monkeypatch.setattr(data_deletion.storage, "delete_trade_objects", cleanup)
    first = data_deletion.delete_all_trades_and_objects(owner)
    assert first.blocked is True and first.remaining == 1
    assert _count(Trade, user_id=owner) == 2
    second = data_deletion.delete_all_trades_and_objects(owner)
    assert second == data_deletion.DeletionOutcome(2, 0, 0, False)


# ── B1: nothing lands between the purge and the row deletion ──────────────


def test_a_screenshot_added_mid_purge_is_purged_before_its_row_is_deleted(
    two_users, monkeypatch
):
    owner = two_users[1]
    trade_id = _trade(owner, "u/%d/t/1/a.png" % owner)
    late = "u/%d/t/1/late.png" % owner
    calls = []
    fake = _cleans_what_is_stored(calls)

    def cleanup(user_id, t):
        result = fake(user_id, t)
        if len(calls) == 1:
            # An upload finishing in another tab, after this trade was purged.
            _add_shot(t, late)
        return result

    monkeypatch.setattr(data_deletion.storage, "delete_trade_objects", cleanup)
    outcome = data_deletion.delete_all_trades_and_objects(owner)
    assert outcome == data_deletion.DeletionOutcome(1, 0, 0, False)
    assert len(calls) == 2
    assert late in calls[1][1], "the late key was never cleaned before its row went"
    assert _count(Trade, id=trade_id) == 0
    assert _count(Screenshot, trade_id=trade_id) == 0


def test_screenshots_that_keep_arriving_block_with_nothing_deleted(
    two_users, monkeypatch
):
    owner = two_users[1]
    trade_id = _trade(owner, "u/%d/t/1/a.png" % owner)
    counter = {"n": 0}
    fake = _cleans_what_is_stored()

    def cleanup(user_id, t):
        result = fake(user_id, t)
        counter["n"] += 1
        _add_shot(t, "u/%d/t/1/late-%d.png" % (owner, counter["n"]))
        return result

    monkeypatch.setattr(data_deletion.storage, "delete_trade_objects", cleanup)
    outcome = data_deletion.delete_all_trades_and_objects(owner)
    assert outcome == data_deletion.DeletionOutcome(0, 1, 0, True)
    assert _count(Trade, id=trade_id) == 1
    assert _count(Screenshot, trade_id=trade_id) == 4


def test_a_trade_created_mid_purge_keeps_its_row_and_its_object_together(
    two_users, monkeypatch
):
    owner = two_users[1]
    purged = _trade(owner, "u/%d/t/1/a.png" % owner)
    created = {}
    fake = _cleans_what_is_stored()

    def cleanup(user_id, t):
        result = fake(user_id, t)
        if not created:
            created["id"] = _trade(owner, "u/%d/t/9/new.png" % owner)
        return result

    monkeypatch.setattr(data_deletion.storage, "delete_trade_objects", cleanup)
    outcome = data_deletion.delete_all_trades_and_objects(owner)
    assert outcome == data_deletion.DeletionOutcome(1, 0, 0, False)
    assert _count(Trade, id=purged) == 0
    # Never purged, so never deleted: the row still names its object.
    assert _count(Trade, id=created["id"]) == 1
    assert _count(Screenshot, trade_id=created["id"]) == 1


def test_bulk_deletion_leaves_no_screenshot_rows_for_purged_trades(
    two_users, monkeypatch
):
    """N2: SQLite does not enforce the cascade here, so it is asserted."""
    owner = two_users[1]
    trade_id = _trade(owner, "u/%d/t/1/a.png" % owner)
    monkeypatch.setattr(
        data_deletion.storage, "delete_trade_objects", _cleans_what_is_stored()
    )
    data_deletion.delete_all_trades_and_objects(owner)
    assert _count(Screenshot, trade_id=trade_id) == 0


# ── account deletion ──────────────────────────────────────────────────────


def test_account_deletion_is_blocked_by_an_incomplete_object_cleanup(
    two_users, monkeypatch
):
    owner = two_users[1]
    _trade(owner, "u/%d/t/1/a.png" % owner)
    monkeypatch.setattr(
        data_deletion.storage,
        "delete_trade_objects",
        lambda u, t: ObjectCleanup(deleted=[], failed=["k"], skipped=[]),
    )
    rows = []
    monkeypatch.setattr(
        data_deletion._account,
        "_delete_account_rows",
        lambda db, u: rows.append(u) or [],
    )
    outcome = data_deletion.delete_account_and_objects(owner)
    assert outcome == data_deletion.DeletionOutcome(0, 1, 0, True)
    assert rows == []
    assert _count(User, id=owner) == 1


def test_account_deletion_is_blocked_by_an_unresolvable_key(two_users, monkeypatch):
    """N4: the account path, not only the bulk path."""
    first, owner = two_users
    _trade(owner, "u/%d/t/9/stolen.png" % first)
    monkeypatch.setattr(
        data_deletion.storage,
        "delete_trade_objects",
        lambda u, t: ObjectCleanup(deleted=[], failed=[], skipped=_paths(t)),
    )
    outcome = data_deletion.delete_account_and_objects(owner)
    assert outcome == data_deletion.DeletionOutcome(0, 0, 1, True)
    assert _count(User, id=owner) == 1


def test_account_deletion_runs_after_a_complete_cleanup(two_users, monkeypatch):
    owner = two_users[1]
    _trade(owner, "u/%d/t/1/a.png" % owner)
    order = []
    fake = _cleans_what_is_stored()
    monkeypatch.setattr(
        data_deletion.storage,
        "delete_trade_objects",
        lambda u, t: order.append("objects") or fake(u, t),
    )
    real_rows = data_deletion._account._delete_account_rows
    monkeypatch.setattr(
        data_deletion._account,
        "_delete_account_rows",
        lambda db, u: order.append("rows") or real_rows(db, u),
    )
    outcome = data_deletion.delete_account_and_objects(owner)
    assert outcome == data_deletion.DeletionOutcome(1, 0, 0, False)
    assert order == ["objects", "rows"]
    assert _count(User, id=owner) == 0


def test_a_missing_account_is_reported_not_blocked(two_users, monkeypatch):
    owner = two_users[1]
    monkeypatch.setattr(data_deletion.storage, "delete_trade_objects", _clean)
    monkeypatch.setattr(
        data_deletion._account, "_delete_account_rows", lambda db, u: None
    )
    outcome = data_deletion.delete_account_and_objects(owner)
    assert outcome == data_deletion.DeletionOutcome(0, 0, 0, False)


def test_a_trade_created_mid_purge_is_purged_before_the_account_goes(
    two_users, monkeypatch
):
    owner = two_users[1]
    _trade(owner, "u/%d/t/1/a.png" % owner)
    calls = []
    fake = _cleans_what_is_stored(calls)
    created = {}

    def cleanup(user_id, t):
        result = fake(user_id, t)
        if not created:
            created["id"] = _trade(owner, "u/%d/t/9/new.png" % owner)
        return result

    monkeypatch.setattr(data_deletion.storage, "delete_trade_objects", cleanup)
    outcome = data_deletion.delete_account_and_objects(owner)
    assert outcome == data_deletion.DeletionOutcome(1, 0, 0, False)
    assert created["id"] in [t for t, _keys in calls], "the new trade was never purged"
    assert _count(User, id=owner) == 0


def test_an_account_whose_trades_keep_arriving_is_not_deleted(two_users, monkeypatch):
    owner = two_users[1]
    _trade(owner, "u/%d/t/1/a.png" % owner)
    fake = _cleans_what_is_stored()

    def cleanup(user_id, t):
        result = fake(user_id, t)
        _trade(owner, "u/%d/t/9/again.png" % owner)
        return result

    monkeypatch.setattr(data_deletion.storage, "delete_trade_objects", cleanup)
    outcome = data_deletion.delete_account_and_objects(owner)
    assert outcome == data_deletion.DeletionOutcome(0, 1, 0, True)
    assert _count(User, id=owner) == 1


def test_a_symlink_named_for_my_trade_to_another_trades_file_is_never_followed(
    two_users, monkeypatch, tmp_path
):
    """Re-review M30: ownership is read from the RESOLVED file name, so a link
    named for my trade that points at another trade's file deletes nothing."""
    first, owner = two_users
    root = tmp_path / "screenshots"
    root.mkdir()
    theirs = _trade(first)
    their_file = root / ("%d_their_chart.png" % theirs)
    their_file.write_bytes(b"theirs")
    mine = _trade(owner)
    link = root / ("%d_mine.png" % mine)
    link.symlink_to(their_file)
    _add_shot(mine, str(link))
    monkeypatch.setattr(data_deletion._account, "SCREENSHOTS_DIR", root)
    monkeypatch.setattr(
        data_deletion.storage,
        "delete_trade_objects",
        lambda u, t: ObjectCleanup(deleted=[], failed=[], skipped=_paths(t)),
    )
    outcome = data_deletion.delete_all_trades_and_objects(owner)
    assert outcome == data_deletion.DeletionOutcome(0, 0, 1, True)
    assert their_file.read_bytes() == b"theirs"
    assert _count(Trade, id=mine) == 1


def test_trade_ones_cleanup_never_removes_trade_twelves_file(monkeypatch, tmp_path):
    """Re-review M06: the prefix is the id AND the separator, so trade 1 does
    not own `12_*`."""
    root = tmp_path / "screenshots"
    root.mkdir()
    other = root / "12_chart.png"
    other.write_bytes(b"twelve")
    monkeypatch.setattr(data_deletion._account, "SCREENSHOTS_DIR", root)
    assert data_deletion._legacy_local_path_resolved(str(other), 1) is False
    assert other.read_bytes() == b"twelve"
    own = root / "1_chart.png"
    own.write_bytes(b"one")
    assert data_deletion._legacy_local_path_resolved(str(own), 1) is True
    assert not own.exists()


def test_project_root_is_the_repository_root():
    """Re-review M08: relative legacy paths are anchored here (S1), so it must
    be the directory that holds `src/` and the migrations, not `src/` itself."""
    from src.tradelens.services import screenshot_service

    root = screenshot_service.PROJECT_ROOT
    assert (root / "src" / "tradelens").is_dir()
    assert (root / "alembic.ini").is_file()
    assert screenshot_service.SCREENSHOTS_DIR == root / "data" / "screenshots"
