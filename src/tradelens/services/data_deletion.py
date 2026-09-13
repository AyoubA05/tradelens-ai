"""Bulk and account deletion: stored objects first, rows only after.

`trade_service.delete_all_trades` and `account.delete_account` erase rows. A
`screenshots` row is the only record of a stored object's key, so removing the
row before the object leaves a private image in the bucket that nothing points
at any more. These wrappers are what the API and the Streamlit Settings page
call instead:

1. every screenshot object of every trade the owner has is removed first,
   through the owner-scoped `storage.delete_trade_objects`;
2. if anything was left behind — a failed delete (retryable) or a key this
   owner may not delete (unresolvable) — **no row is deleted**, and the
   outcome says how much was left and of which kind;
3. only a complete cleanup earns the row deletion.

Nothing here reports success over a bucket that still holds an owned object
that should have been removed.

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
from typing import List, Tuple

from src.tradelens.api import storage
from src.tradelens.db.models import Trade
from src.tradelens.db.session import SessionLocal
from src.tradelens.services import account as _account
from src.tradelens.services.account import _resolve_owned_files, delete_account
from src.tradelens.services.ownership import require_user_id
from src.tradelens.services.trade_service import delete_all_trades


@dataclass(frozen=True)
class DeletionOutcome:
    """What a bulk or account deletion did.

    `deleted` is a row count (trades, or 1/0 for the account). `remaining`
    counts objects that failed to delete — a retry can clear them.
    `unresolvable` counts stored paths this owner may not delete — a retry
    cannot. `blocked` is true whenever either is non-zero, and then `deleted`
    is always 0.
    """

    deleted: int
    remaining: int
    unresolvable: int
    blocked: bool


def _owned_trade_ids(owner: int) -> List[int]:
    db = SessionLocal()
    try:
        return [
            row_id
            for (row_id,) in db.query(Trade.id).filter(Trade.user_id == owner).all()
        ]
    finally:
        db.close()


def _legacy_local_path_resolved(key: str) -> bool:
    """Whether a skipped, non-R2 key is a legacy file we may treat as removed.

    Decision S8 (owner-approved): legacy cleanup is idempotent and confined to
    the approved legacy screenshot root, `account.SCREENSHOTS_DIR`.

    * A path that resolves inside that root is unlinked; one that is already
      missing counts as already gone.
    * Anything else — another tenant's R2 key, an absolute path elsewhere, a
      `..` escape, or a symlink inside the root that resolves outside it — is
      never deleted and stays unresolvable. `_resolve_owned_files` resolves
      symlinks before checking containment, so a link cannot smuggle a target
      out of the root.

    The root is read through the module at call time, so a patched directory
    applies (the system-message sweep forbids `globals()` in services).
    """
    resolved = _resolve_owned_files([key], root=Path(_account.SCREENSHOTS_DIR))
    if not resolved:
        return False
    for path in resolved:
        try:
            path.unlink()
        except FileNotFoundError:
            continue
        except OSError:
            # Present but not removable: not gone, so not resolved.
            return False
    return True


def purge_trade_screenshots(user_id: int) -> Tuple[int, int]:
    """Remove every stored screenshot object of every trade this owner has.

    Returns `(remaining, unresolvable)`. Never raises for an object-store
    fault; `delete_trade_objects` reports it in its result instead.
    """
    owner = require_user_id(user_id)
    remaining = 0
    unresolvable = 0
    for trade_id in _owned_trade_ids(owner):
        cleanup = storage.delete_trade_objects(owner, trade_id)
        remaining += len(cleanup.failed)
        unresolvable += sum(
            1 for key in cleanup.skipped if not _legacy_local_path_resolved(key)
        )
    return remaining, unresolvable


def delete_all_trades_and_objects(user_id: int) -> DeletionOutcome:
    """Delete every trade this owner has — only after all their objects are gone."""
    owner = require_user_id(user_id)
    remaining, unresolvable = purge_trade_screenshots(owner)
    if remaining or unresolvable:
        return DeletionOutcome(0, remaining, unresolvable, True)
    return DeletionOutcome(delete_all_trades(owner), 0, 0, False)


def delete_account_and_objects(user_id: int) -> DeletionOutcome:
    """Delete this account — only after all its trades' objects are gone."""
    owner = require_user_id(user_id)
    remaining, unresolvable = purge_trade_screenshots(owner)
    if remaining or unresolvable:
        return DeletionOutcome(0, remaining, unresolvable, True)
    return DeletionOutcome(1 if delete_account(owner) else 0, 0, 0, False)
