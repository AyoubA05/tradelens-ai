"""Account lifecycle: deleting an account and everything it owns.

Deletion here is **hard**, not a flag. The point of the capability is that
`/privacy` can say "you can delete your account and its data" and have it
be true; a soft delete would leave every trade, psychology note, and chart
image in the database while telling the user they were gone. `is_active`
already exists separately for suspending an account without erasing it.

Two things are deliberately not deleted:

* AI cost rows are kept with `user_id` set to NULL. They are the operator's
  spend accounting, and once unlinked they say nothing about a person. The
  privacy policy states this rather than implying total erasure.
* Files outside the screenshots directory are never touched, even if a row
  points at one. A stored path must not be able to delete arbitrary files.

Streamlit-free.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Iterable

from sqlalchemy.orm import Session

from src.tradelens.db.models import (
    AIAnalysis,
    AIUsageLog,
    Correction,
    PerformanceMetrics,
    Screenshot,
    Strategy,
    Trade,
    User,
    UserSetting,
    WeeklyReview,
)
from src.tradelens.db.session import SessionLocal
from src.tradelens.services.screenshot_service import SCREENSHOTS_DIR as _SHOTS_DIR

_log = logging.getLogger(__name__)

# Sourced from the service that writes them, so the two cannot drift and
# leave deletion looking in the wrong place. Patched in tests.
SCREENSHOTS_DIR = Path(_SHOTS_DIR)

# Tables whose user_id is cleared rather than whose rows are removed.
ANONYMISED = frozenset({"ai_usage_log"})

# Deleted wholesale by owner. Kept as a list so the sweep is explicit and a
# reviewer can see every table that holds personal data in one place.
_OWNED_BY_USER = (
    Strategy,
    UserSetting,
    WeeklyReview,
    PerformanceMetrics,
    Correction,
)


def _resolve_owned_files(paths: Iterable[str]) -> list[Path]:
    """Absolute paths that are genuinely inside the screenshots directory.

    Anything else — an absolute path elsewhere, or one escaping via `..` —
    is dropped rather than deleted.
    """
    try:
        root = SCREENSHOTS_DIR.resolve()
    except OSError:  # pragma: no cover — unreadable root
        return []

    safe: list[Path] = []
    for raw in paths:
        if not raw:
            continue
        try:
            candidate = Path(raw).resolve()
            candidate.relative_to(root)
        except (ValueError, OSError):
            _log.warning("Refusing to delete a path outside the screenshot store")
            continue
        safe.append(candidate)
    return safe


def _delete_files(paths: Iterable[Path]) -> None:
    """Best-effort removal. A missing or locked file must not abort deletion
    and leave the account half-erased."""
    for path in paths:
        try:
            path.unlink()
        except FileNotFoundError:
            continue
        except OSError:  # pragma: no cover — permissions vary by host
            _log.warning("Could not remove a screenshot during account deletion")


def delete_account(user_id: int) -> bool:
    """Erase a user and every record they own. Returns whether one existed.

    The whole sweep runs in a single transaction, so a failure part-way
    leaves the account intact rather than partially deleted.
    """
    db: Session = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if user is None:
            return False

        trade_ids = [
            row_id
            for (row_id,) in db.query(Trade.id).filter(Trade.user_id == user_id).all()
        ]

        # Read the file paths before the rows that name them are gone.
        stored_paths: list[str] = []
        if trade_ids:
            stored_paths = [
                path
                for (path,) in db.query(Screenshot.file_path)
                .filter(Screenshot.trade_id.in_(trade_ids))
                .all()
            ]

        if trade_ids:
            for model in (Screenshot, AIAnalysis, Correction):
                db.query(model).filter(model.trade_id.in_(trade_ids)).delete(
                    synchronize_session=False
                )
            db.query(Trade).filter(Trade.id.in_(trade_ids)).delete(
                synchronize_session=False
            )

        for model in _OWNED_BY_USER:
            db.query(model).filter(model.user_id == user_id).delete(
                synchronize_session=False
            )

        # Spend accounting outlives the account, minus the link to a person.
        db.query(AIUsageLog).filter(AIUsageLog.user_id == user_id).update(
            {AIUsageLog.user_id: None}, synchronize_session=False
        )

        db.query(User).filter(User.id == user_id).delete(synchronize_session=False)
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

    # Files last: the database is the record of what exists, so it is
    # committed before anything on disk is irreversibly removed.
    _delete_files(_resolve_owned_files(stored_paths))
    return True
