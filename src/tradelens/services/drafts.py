"""Owner-scoped read/write of the single in-progress New Trade draft.

A draft is never a `Trade` row (Decision 3, `db/models.py::TradeDraft`).
`save_draft` supersedes rather than accumulates: `trade_drafts.user_id` is
unique, so there is exactly one draft per owner at any time, and a repeated
save overwrites it rather than growing an unbounded backlog. No Streamlit
imports here.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Optional

from src.tradelens.db.models import TradeDraft
from src.tradelens.db.session import SessionLocal
from src.tradelens.services.ownership import require_user_id


def _now() -> datetime:
    return datetime.now(timezone.utc)


def get_draft(user_id: int) -> Optional[dict]:
    """Return the owner's saved draft payload, or None if they have none.

    The `user_id` filter is not optional decoration — it is the entire reason
    this function is safe to call with an id taken from the session. Drop it
    and this becomes "read the most recently saved draft of anyone."
    """
    owner = require_user_id(user_id)
    db = SessionLocal()
    try:
        row = db.query(TradeDraft).filter(TradeDraft.user_id == owner).first()
        if row is None:
            return None
        return json.loads(row.payload_json)
    finally:
        db.close()


def save_draft(user_id: int, payload: dict) -> None:
    """Persist `payload` as the owner's one live draft, replacing any prior one.

    Read-then-write rather than an upsert: `trade_drafts.user_id` is unique,
    so a stray second row would fail the constraint immediately rather than
    silently drift, and this function is the only write path into the table.
    """
    owner = require_user_id(user_id)
    db = SessionLocal()
    try:
        row = db.query(TradeDraft).filter(TradeDraft.user_id == owner).first()
        now = _now()
        if row is None:
            row = TradeDraft(
                user_id=owner,
                payload_json=json.dumps(payload),
                created_at=now,
                updated_at=now,
            )
            db.add(row)
        else:
            row.payload_json = json.dumps(payload)
            row.updated_at = now
        db.commit()
    finally:
        db.close()


def delete_draft(user_id: int) -> None:
    """Remove the owner's draft, if any. A no-op when they have none."""
    owner = require_user_id(user_id)
    db = SessionLocal()
    try:
        db.query(TradeDraft).filter(TradeDraft.user_id == owner).delete()
        db.commit()
    finally:
        db.close()
