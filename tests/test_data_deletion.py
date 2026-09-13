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
from src.tradelens.db.models import Screenshot, Trade, TradeSummaryResult
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
        return ObjectCleanup(deleted=["k"], failed=[], skipped=[])

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


def test_a_legacy_file_inside_the_root_is_removed_and_does_not_block(
    two_users, monkeypatch, tmp_path
):
    owner = two_users[1]
    root = tmp_path / "screenshots"
    root.mkdir()
    legacy = root / "old.png"
    legacy.write_bytes(b"png")
    _trade(owner, str(legacy))
    monkeypatch.setattr(data_deletion._account, "SCREENSHOTS_DIR", root)
    monkeypatch.setattr(
        data_deletion.storage,
        "delete_trade_objects",
        lambda u, t: ObjectCleanup(deleted=[], failed=[], skipped=[str(legacy)]),
    )
    outcome = data_deletion.delete_all_trades_and_objects(owner)
    assert outcome == data_deletion.DeletionOutcome(1, 0, 0, False)
    assert not legacy.exists()


def test_a_missing_legacy_file_inside_the_root_counts_as_already_gone(
    two_users, monkeypatch, tmp_path
):
    owner = two_users[1]
    root = tmp_path / "screenshots"
    root.mkdir()
    gone = root / "never-there.png"
    _trade(owner, str(gone))
    monkeypatch.setattr(data_deletion._account, "SCREENSHOTS_DIR", root)
    monkeypatch.setattr(
        data_deletion.storage,
        "delete_trade_objects",
        lambda u, t: ObjectCleanup(deleted=[], failed=[], skipped=[str(gone)]),
    )
    outcome = data_deletion.delete_all_trades_and_objects(owner)
    assert outcome == data_deletion.DeletionOutcome(1, 0, 0, False)


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


def test_legacy_cleanup_is_idempotent_across_a_retry(two_users, monkeypatch, tmp_path):
    owner = two_users[1]
    root = tmp_path / "screenshots"
    root.mkdir()
    legacy = root / "old.png"
    legacy.write_bytes(b"png")
    _trade(owner, str(legacy))
    _trade(owner, "u/%d/t/2/b.png" % owner)
    monkeypatch.setattr(data_deletion._account, "SCREENSHOTS_DIR", root)
    attempts = {"n": 0}

    def cleanup(user_id, trade_id):
        db = SessionLocal()
        try:
            path = (
                db.query(Screenshot.file_path)
                .filter(Screenshot.trade_id == trade_id)
                .scalar()
            )
        finally:
            db.close()
        if path.startswith("u/"):
            attempts["n"] += 1
            failed = ["k"] if attempts["n"] == 1 else []
            return ObjectCleanup(deleted=[], failed=failed, skipped=[])
        return ObjectCleanup(deleted=[], failed=[], skipped=[path])

    monkeypatch.setattr(data_deletion.storage, "delete_trade_objects", cleanup)
    first = data_deletion.delete_all_trades_and_objects(owner)
    assert first.blocked is True and first.remaining == 1
    second = data_deletion.delete_all_trades_and_objects(owner)
    assert second == data_deletion.DeletionOutcome(2, 0, 0, False)


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
    deleted = []
    monkeypatch.setattr(
        data_deletion, "delete_account", lambda u: deleted.append(u) or True
    )
    outcome = data_deletion.delete_account_and_objects(owner)
    assert outcome == data_deletion.DeletionOutcome(0, 1, 0, True)
    assert deleted == []


def test_account_deletion_runs_after_a_complete_cleanup(two_users, monkeypatch):
    owner = two_users[1]
    _trade(owner, "u/%d/t/1/a.png" % owner)
    order = []
    monkeypatch.setattr(
        data_deletion.storage,
        "delete_trade_objects",
        lambda u, t: order.append("objects") or ObjectCleanup(["k"], [], []),
    )
    monkeypatch.setattr(
        data_deletion, "delete_account", lambda u: order.append("rows") or True
    )
    outcome = data_deletion.delete_account_and_objects(owner)
    assert outcome == data_deletion.DeletionOutcome(1, 0, 0, False)
    assert order == ["objects", "rows"]


def test_a_missing_account_is_reported_not_blocked(two_users, monkeypatch):
    owner = two_users[1]
    monkeypatch.setattr(data_deletion.storage, "delete_trade_objects", _clean)
    monkeypatch.setattr(data_deletion, "delete_account", lambda u: False)
    outcome = data_deletion.delete_account_and_objects(owner)
    assert outcome == data_deletion.DeletionOutcome(0, 0, 0, False)
