"""Bulk and account deletion: stored objects first, rows only after.

`screenshots` rows are the only record of a stored object's key, so removing a
row before its object leaves a private image in the bucket that nothing points
at any more. These are what the API and the Streamlit Settings page call:

1. every screenshot object of every trade the owner has is removed first,
   through the owner-scoped `storage.delete_trade_objects`, recording exactly
   which keys each trade's cleanup handled;
2. if anything was left behind — a failed delete (retryable) or a key this
   owner may not delete (unresolvable) — **no row is deleted**, and the
   outcome says how much was left and of which kind;
3. then, in one transaction that locks the purged trades, the rows are deleted
   **only for the trades whose objects were purged**, and only if no screenshot
   row now names a key that cleanup never handled.

Step 3 closes a race (Phase 9 Group A review, B1): a screenshot or trade that
lands while objects are being removed would otherwise lose its row while its
object stays in the bucket. A mismatch rolls back and the whole purge runs
again, a bounded number of times; if uploads keep arriving, nothing is deleted
and the outcome is a retryable block. Nothing here reports success over an
owned object that should have been removed.

A trade created after the purge read the trade list is not part of the
deletion: its rows and its objects are left together, still pointing at each
other. Account deletion refuses instead (a trade the account still owns would
block the user delete), and re-purges.

A retry after a partial cleanup converges: `delete_trade_objects` treats an
already-absent object as deleted, and a legacy file that is already gone
counts as removed. Objects removed on a blocked attempt stay removed while
their rows remain, so the trade detail shows the designed "chart no longer
available" state until the retry completes.

Streamlit-free.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, FrozenSet, List, Tuple
from urllib.parse import urlsplit

from src.tradelens.api import storage
from src.tradelens.db.models import (
    AIAnalysis,
    AIJob,
    Correction,
    DailyDebrief,
    Screenshot,
    Trade,
    TradeSummaryResult,
    User,
    WeeklyReview,
)
from src.tradelens.db.session import SessionLocal
from src.tradelens.services import account as _account
from src.tradelens.services.account import _resolve_owned_files
from src.tradelens.services.ownership import require_user_id

# Passes of purge-then-verify before giving up on an owner whose uploads keep
# landing mid-deletion. Each pass is idempotent; three is plenty for a human.
_MAX_ATTEMPTS = 3


@dataclass(frozen=True)
class DeletionOutcome:
    """What a bulk or account deletion did.

    `deleted` is a row count (trades, or 1/0 for the account). `remaining`
    counts objects that could not be removed — a retry can clear them.
    `unresolvable` counts stored paths this owner may not delete — a retry
    cannot. `blocked` is true whenever either is non-zero, and then `deleted`
    is always 0.
    """

    deleted: int
    remaining: int
    unresolvable: int
    blocked: bool


class ScreenshotCleanupBlocked(RuntimeError):
    """A row deletion was refused because its private object cleanup failed."""

    def __init__(self, outcome: DeletionOutcome):
        super().__init__("screenshot_cleanup_failed")
        self.outcome = outcome


@dataclass(frozen=True)
class _Purge:
    handled: Dict[int, FrozenSet[str]]
    remaining: int
    unresolvable: int


def _owned_trade_ids(owner: int, *, samples_only: bool = False) -> List[int]:
    db = SessionLocal()
    try:
        query = db.query(Trade.id).filter(Trade.user_id == owner)
        if samples_only:
            query = query.filter(Trade.is_sample == 1)
        return [row_id for (row_id,) in query.all()]
    finally:
        db.close()


def _legacy_local_path_resolved(key: str, trade_id: int) -> bool:
    """Whether a skipped, non-R2 key is this trade's legacy file, now gone.

    Decision S8 (owner-approved): legacy cleanup is idempotent and confined to
    the approved legacy screenshot root, `account.SCREENSHOTS_DIR`.

    * The path must resolve inside that root **and** be named for this trade:
      the legacy writer stored `SCREENSHOTS_DIR / f"{trade_id}_{name}"`. A row
      naming another trade's file — another tenant's, even inside the root —
      is never deleted (Phase 9 Group A review, B2).
    * A matching file that is already missing counts as already gone.
    * Anything else — an R2 key of another tenant, an absolute path elsewhere,
      a `..` escape, a symlink resolving outside the root, or a file that is
      present but cannot be removed — stays unresolvable.

    The root is read through the module at call time, so a patched directory
    applies (the system-message sweep forbids `globals()` in services).
    """
    # The legacy Streamlit form also stored remote screenshot URLs directly.
    # They name neither an R2 object nor a local file we control, so removing
    # their database reference is the complete cleanup. No network request is
    # made and an encoded/malformed scheme does not enter this branch.
    try:
        remote = urlsplit(key)
    except ValueError:
        remote = None
    if (
        remote is not None
        and remote.scheme.lower() in ("http", "https")
        and bool(remote.netloc)
    ):
        return True

    resolved = _resolve_owned_files([key], root=Path(_account.SCREENSHOTS_DIR))
    if not resolved:
        return False
    prefix = "{}_".format(int(trade_id))
    for path in resolved:
        if not path.name.startswith(prefix):
            return False
        try:
            path.unlink()
        except FileNotFoundError:
            continue
        except OSError:
            # Present but not removable: not gone, so not resolved.
            return False
    return True


def _purge(owner: int, *, samples_only: bool = False) -> _Purge:
    handled: Dict[int, FrozenSet[str]] = {}
    remaining = 0
    unresolvable = 0
    for trade_id in _owned_trade_ids(owner, samples_only=samples_only):
        cleanup = storage.delete_trade_objects(owner, trade_id)
        remaining += len(cleanup.failed)
        keys = set(cleanup.deleted)
        for key in cleanup.skipped:
            if _legacy_local_path_resolved(key, trade_id):
                keys.add(key)
            else:
                unresolvable += 1
        handled[trade_id] = frozenset(keys)
    return _Purge(handled, remaining, unresolvable)


def purge_trade_screenshots(user_id: int) -> Tuple[int, int]:
    """Remove every stored screenshot object of every trade this owner has.

    Returns `(remaining, unresolvable)`. Never raises for an object-store
    fault; `delete_trade_objects` reports it in its result instead.
    """
    purge = _purge(require_user_id(user_id))
    return purge.remaining, purge.unresolvable


def _lock_and_verify(db, owner: int, handled: Dict[int, FrozenSet[str]]) -> bool:
    """Lock the purged trades, then confirm cleanup handled every key they name.

    `FOR UPDATE` on PostgreSQL makes a concurrent screenshot insert for these
    trades wait for this transaction (and then fail its foreign key, because
    the trade is gone) instead of slipping in between the check and the delete.
    SQLite ignores the clause, and pysqlite opens the write transaction only
    at the first DELETE, so on SQLite a screenshot committed by another
    connection between this check and the delete is NOT excluded. The race
    guarantee holds on PostgreSQL only; real-PostgreSQL concurrency remains a
    pre-release gate (re-review should-fix 2).
    """
    ids = sorted(handled)
    if not ids:
        return True
    db.query(Trade.id).filter(
        Trade.user_id == owner, Trade.id.in_(ids)
    ).with_for_update().all()
    rows = (
        db.query(Screenshot.trade_id, Screenshot.file_path)
        .filter(Screenshot.trade_id.in_(ids))
        .all()
    )
    return all(path in handled.get(trade_id, frozenset()) for trade_id, path in rows)


def _delete_purged_trades(
    db, owner: int, ids: List[int], *, samples_only: bool = False
) -> int:
    if not ids:
        return 0
    for model in (Correction, AIAnalysis, Screenshot):
        db.query(model).filter(model.trade_id.in_(ids)).delete(
            synchronize_session=False
        )
    query = db.query(Trade).filter(Trade.user_id == owner, Trade.id.in_(ids))
    if samples_only:
        query = query.filter(Trade.is_sample == 1)
    return query.delete(synchronize_session=False)


DERIVED_JOB_KINDS = ("trade_summary", "weekly_recap", "daily_debrief")


def _delete_derived_review_state(db, owner: int) -> None:
    """Remove generated prose, and queued snapshots, derived from the owner's trades.

    Decision S7 (summaries) extended by Phase 10A R8/C5: weekly recaps and daily
    debriefs quote trades and notes, and their job payloads carry snapshots. A
    worker still running after this commits cannot write them back: review
    saves lock their source trades and fail closed when any is gone.
    """
    db.query(AIJob).filter(
        AIJob.user_id == owner, AIJob.kind.in_(DERIVED_JOB_KINDS)
    ).delete(synchronize_session=False)
    for model in (TradeSummaryResult, WeeklyReview, DailyDebrief):
        db.query(model).filter(model.user_id == owner).delete(synchronize_session=False)


def delete_sample_trades_and_objects(user_id: int) -> DeletionOutcome:
    """Delete this owner's seeded trades without orphaning acquired screenshots.

    Sample rows are ordinary editable trades after insertion. They can therefore
    gain screenshots and AI detail before the user presses Clear or Load again;
    the row-only legacy helper is not a safe deletion boundary for them.
    """
    owner = require_user_id(user_id)
    for _attempt in range(_MAX_ATTEMPTS):
        purge = _purge(owner, samples_only=True)
        if purge.remaining or purge.unresolvable:
            return DeletionOutcome(0, purge.remaining, purge.unresolvable, True)
        db = SessionLocal()
        try:
            if not _lock_and_verify(db, owner, purge.handled):
                db.rollback()
                continue
            deleted = _delete_purged_trades(
                db, owner, sorted(purge.handled), samples_only=True
            )
            if purge.handled:
                # A filtered summary, weekly recap or daily debrief can include
                # any one of these samples, and its job payload contains trade data. There is no
                # safe result to retain once a source row is removed.
                _delete_derived_review_state(db, owner)
            db.commit()
            return DeletionOutcome(deleted, 0, 0, False)
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
    return DeletionOutcome(0, 1, 0, True)


def delete_all_trades_and_objects(user_id: int) -> DeletionOutcome:
    """Delete every trade this owner has — only after all their objects are gone."""
    owner = require_user_id(user_id)
    for _attempt in range(_MAX_ATTEMPTS):
        purge = _purge(owner)
        if purge.remaining or purge.unresolvable:
            return DeletionOutcome(0, purge.remaining, purge.unresolvable, True)
        db = SessionLocal()
        try:
            if not _lock_and_verify(db, owner, purge.handled):
                # A screenshot landed after its trade was purged: go round again.
                db.rollback()
                continue
            deleted = _delete_purged_trades(db, owner, sorted(purge.handled))
            # Decisions S7/R8: summaries and reviews are derived from these trades
            # and can quote their notes, so they go too — including leftovers with no trades.
            _delete_derived_review_state(db, owner)
            db.commit()
            return DeletionOutcome(deleted, 0, 0, False)
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
    return DeletionOutcome(0, 1, 0, True)


def delete_account_and_objects(user_id: int) -> DeletionOutcome:
    """Delete this account — only after all its trades' objects are gone."""
    owner = require_user_id(user_id)
    for _attempt in range(_MAX_ATTEMPTS):
        purge = _purge(owner)
        if purge.remaining or purge.unresolvable:
            return DeletionOutcome(0, purge.remaining, purge.unresolvable, True)
        db = SessionLocal()
        try:
            # Serialise with every other owner-locked writer for this account.
            db.query(User.id).filter(User.id == owner).with_for_update().first()
            if not _lock_and_verify(db, owner, purge.handled):
                db.rollback()
                continue
            current = {
                trade_id
                for (trade_id,) in db.query(Trade.id)
                .filter(Trade.user_id == owner)
                .all()
            }
            if current - set(purge.handled):
                # A trade appeared after the purge read the list; its objects
                # were never removed, so it must go round again first.
                db.rollback()
                continue
            if _account._delete_account_rows(db, owner) is None:
                db.rollback()
                return DeletionOutcome(0, 0, 0, False)
            db.commit()
            return DeletionOutcome(1, 0, 0, False)
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()
    return DeletionOutcome(0, 1, 0, True)
