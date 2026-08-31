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


# Draft keys the AI autofill worker owns. The browser's autosave body is
# built by `toDraftPayload`, which deliberately never sets them, so "the
# incoming payload does not mention this key" reliably means "an autosave,
# not an intent to clear."
WORKER_OWNED_DRAFT_KEYS = frozenset({"ai_suggestions", "ai_suggestions_screenshot_id"})


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

    Keys in `WORKER_OWNED_DRAFT_KEYS` are the one exception to "replacing":
    they are written by the autofill worker, never by the trader's form, and
    the browser's autosave body does not contain them. A plain wholesale
    replace therefore meant that an autosave PUT landing a moment after the
    worker finished DELETED that job's suggestions — and because the enqueue
    idempotency key is the screenshot, re-requesting autofill returns the
    same already-succeeded job forever, so the paid vision reading was gone
    for good. Carrying a stored worker key forward when the incoming payload
    does not mention it makes an autosave incapable of destroying it. A
    caller that genuinely means to clear them (there is one: `delete_draft`
    after the trade is journaled) removes the row instead.
    """
    owner = require_user_id(user_id)
    db = SessionLocal()
    try:
        row = db.query(TradeDraft).filter(TradeDraft.user_id == owner).first()
        now = _now()
        merged = dict(payload)
        if row is not None:
            stored = json.loads(row.payload_json)
            for key in WORKER_OWNED_DRAFT_KEYS:
                # Absent, not "present and null": an explicit null from a
                # caller that names the key is still that caller's decision.
                if key not in merged and key in stored:
                    merged[key] = stored[key]
        if row is None:
            row = TradeDraft(
                user_id=owner,
                payload_json=json.dumps(merged),
                created_at=now,
                updated_at=now,
            )
            db.add(row)
        else:
            row.payload_json = json.dumps(merged)
            row.updated_at = now
        db.commit()
    finally:
        db.close()


def delete_draft(user_id: int) -> None:
    """Remove the owner's draft, if any. A no-op when they have none.

    This is a draft's end of life, and it is the reason a draft cannot leak
    into the next trade. `POST /v1/trades` calls it once the trade is
    durable: what the draft described is now a journal entry, so anything
    still in it is stale, and the mount-time prefill in the browser fills
    any field still at its empty default from whatever the draft holds. Left
    alive, the next New Trade would open carrying the previous trade's asset,
    entry time and four prices — an entry that looks deliberate rather than
    half-finished. Server-side is where this has to happen: it holds even if
    that browser tab never comes back.
    """
    owner = require_user_id(user_id)
    db = SessionLocal()
    try:
        db.query(TradeDraft).filter(TradeDraft.user_id == owner).delete()
        db.commit()
    finally:
        db.close()
