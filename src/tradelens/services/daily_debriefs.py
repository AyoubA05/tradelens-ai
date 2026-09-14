"""Saved daily debriefs — owner-scoped, replaced only on success, source-locked.

Phase 10A (decisions R1, R8, C1, C3, C5). Every review save made by the job
path runs one transaction that:

1. locks the source trades `FOR UPDATE` and fails closed (`ReviewSourceGone`)
   if any is missing or belongs to someone else;
2. calls the caller's `verify(db)` against that locked state — the job worker
   recomputes the effective-input fingerprint there — and fails closed
   (`ReviewSourceChanged`) when it returns False;
3. only then writes, stamping provenance.

So a worker still running after delete-all cannot resurrect a note. On SQLite
`FOR UPDATE` is ignored; the guarantee under true concurrency holds on
PostgreSQL (the same caveat as `data_deletion._lock_and_verify`).

Streamlit-free.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Callable, List, Optional

from sqlalchemy.orm import Session

from src.tradelens.db.models import DailyDebrief, Trade
from src.tradelens.db.session import SessionLocal
from src.tradelens.services.ownership import require_user_id

Verifier = Callable[[Session], bool]


class ReviewSourceGone(RuntimeError):
    """A source trade was deleted before the review could be saved."""


class ReviewSourceChanged(ReviewSourceGone):
    """The locked sources no longer produce the input the review was made from."""


def lock_and_verify_sources(
    db: Session, owner: int, source_trade_ids: List[int], verify: Verifier
) -> None:
    """Lock the owner's source trades, then run the caller's check. Raises on failure."""
    ids = {int(i) for i in source_trade_ids}
    if not ids:
        raise ReviewSourceGone("review source is gone")
    present = {
        tid
        for (tid,) in db.query(Trade.id)
        .filter(Trade.user_id == owner, Trade.id.in_(sorted(ids)))
        .with_for_update()
        .all()
    }
    if present != ids:
        raise ReviewSourceGone("review source is gone")
    if verify(db) is not True:
        raise ReviewSourceChanged("review source changed")


def _to_dict(row: DailyDebrief) -> dict:
    try:
        stats = json.loads(row.stats_json or "{}")
    except (json.JSONDecodeError, TypeError):
        stats = {}
    return {
        "id": row.id,
        "day": row.day,
        "content_md": row.content_md,
        "stats": stats,
        "reviewed_trades": row.reviewed_trades,
        "input_fingerprint": row.input_fingerprint,
        "job_id": row.job_id,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def save_daily_debrief(
    *,
    user_id: int,
    day: str,
    input_fingerprint: str,
    job_id: Optional[int],
    result: dict,
    source_trade_ids: List[int],
    verify: Verifier,
) -> int:
    """Save (or replace) the owner's debrief for `day`; returns the row id.

    Writes nothing unless every source trade exists for this owner and
    `verify(db)` returns True inside the locked transaction.
    """
    owner = require_user_id(user_id)
    db = SessionLocal()
    try:
        lock_and_verify_sources(db, owner, source_trade_ids, verify)
        now = datetime.now(timezone.utc)
        row = (
            db.query(DailyDebrief)
            .filter(DailyDebrief.user_id == owner, DailyDebrief.day == day)
            .with_for_update()
            .first()
        )
        if row is None:
            row = DailyDebrief(user_id=owner, day=day, created_at=now)
            db.add(row)
        row.input_fingerprint = str(input_fingerprint)
        row.job_id = None if job_id is None else int(job_id)
        row.content_md = str(result["content_md"])
        row.stats_json = json.dumps(
            result.get("stats") or {}, allow_nan=False, default=str
        )
        row.reviewed_trades = int(result["reviewed_trades"])
        row.updated_at = now
        db.commit()
        return int(row.id)
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_daily_debrief(*, user_id: int, day: str) -> Optional[dict]:
    owner = require_user_id(user_id)
    db = SessionLocal()
    try:
        row = (
            db.query(DailyDebrief)
            .filter(DailyDebrief.user_id == owner, DailyDebrief.day == day)
            .first()
        )
        return _to_dict(row) if row else None
    finally:
        db.close()


def get_daily_debrief_by_id(result_id: int, user_id: int) -> Optional[dict]:
    owner = require_user_id(user_id)
    db = SessionLocal()
    try:
        row = (
            db.query(DailyDebrief)
            .filter(DailyDebrief.id == result_id, DailyDebrief.user_id == owner)
            .first()
        )
        return _to_dict(row) if row else None
    finally:
        db.close()
