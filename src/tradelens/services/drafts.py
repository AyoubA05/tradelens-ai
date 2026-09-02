"""Owner-scoped read/write of the single in-progress New Trade draft.

A draft is never a `Trade` row (Decision 3, `db/models.py::TradeDraft`).
`save_draft` supersedes rather than accumulates: `trade_drafts.user_id` is
unique, so there is exactly one draft per owner at any time, and a repeated
save overwrites it rather than growing an unbounded backlog. No Streamlit
imports here.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError

from src.tradelens.db.models import TradeDraft
from src.tradelens.db.session import SessionLocal
from src.tradelens.services.ownership import require_user_id


# Draft keys the AI autofill worker owns. The browser's autosave body is
# built by `toDraftPayload`, which deliberately never sets them, so "the
# incoming payload does not mention this key" reliably means "an autosave,
# not an intent to clear."
WORKER_OWNED_DRAFT_KEYS = frozenset(
    {
        "ai_suggestions",
        "ai_suggestions_screenshot_id",
        "ai_suggestions_job_id",
    }
)


@dataclass(frozen=True)
class DraftSnapshot:
    """One owner's current form view and its concurrency revision."""

    payload: Optional[dict]
    revision: int
    retired: bool


def _now() -> datetime:
    return datetime.now(timezone.utc)


def get_draft_snapshot(user_id: int, *, include_retired: bool = False) -> DraftSnapshot:
    """Read the row plus the revision browser writes must compare against."""
    owner = require_user_id(user_id)
    db = SessionLocal()
    try:
        row = db.query(TradeDraft).filter(TradeDraft.user_id == owner).first()
        if row is None:
            return DraftSnapshot(payload=None, revision=0, retired=False)
        retired = row.retired_at is not None
        payload = json.loads(row.payload_json)
        return DraftSnapshot(
            payload=payload if include_retired or not retired else None,
            revision=int(row.revision),
            retired=retired,
        )
    finally:
        db.close()


def get_draft(user_id: int) -> Optional[dict]:
    """Return the owner's saved draft payload, or None if they have none.

    The `user_id` filter is not optional decoration — it is the entire reason
    this function is safe to call with an id taken from the session. Drop it
    and this becomes "read the most recently saved draft of anyone."
    """
    return get_draft_snapshot(user_id).payload


def get_worker_draft(user_id: int) -> Optional[dict]:
    """Read suggestion metadata even when the completed form is retired.

    Retired payload is invisible to New Trade's GET, but the autofill poll
    still needs the exact result its worker wrote after the trade was saved.
    """
    return get_draft_snapshot(user_id, include_retired=True).payload


def save_draft(user_id: int, payload: dict) -> None:
    """Persist `payload` as the owner's one live draft, replacing any prior one.

    Read-then-write rather than an upsert: `trade_drafts.user_id` is unique,
    so a stray second row would fail the constraint immediately rather than
    silently drift. This is the trusted/internal replacement path; browser
    writes use `save_form_draft`'s revision precondition instead.

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
            row.revision = int(row.revision) + 1
            row.retired_at = None
            row.updated_at = now
        db.commit()
    finally:
        db.close()


def save_form_draft(
    user_id: int, payload: dict, *, expected_revision: int
) -> Optional[int]:
    """Conditionally save one browser draft and return its new revision.

    ``None`` is a stale write.  The condition and update are one SQL statement;
    checking the revision in Python would recreate the same lost-update window
    this function exists to close.
    """
    owner = require_user_id(user_id)
    if isinstance(expected_revision, bool) or expected_revision < 0:
        raise ValueError("expected_revision must be non-negative")
    db = SessionLocal()
    try:
        row = (
            db.query(TradeDraft.payload_json, TradeDraft.retired_at)
            .filter(
                TradeDraft.user_id == owner,
                TradeDraft.revision == expected_revision,
            )
            .first()
        )
        if row is not None:
            merged = dict(payload)
            # Suggestions written onto an active form survive autosave.  A
            # retired row belongs to the trade that just completed, so a new
            # form deliberately starts without those worker-owned values.
            if row.retired_at is None:
                stored = json.loads(row.payload_json)
                for key in WORKER_OWNED_DRAFT_KEYS:
                    if key in stored:
                        merged[key] = stored[key]
            written = db.execute(
                update(TradeDraft)
                .where(
                    TradeDraft.user_id == owner,
                    TradeDraft.revision == expected_revision,
                )
                .values(
                    payload_json=json.dumps(merged),
                    revision=expected_revision + 1,
                    retired_at=None,
                    updated_at=_now(),
                )
                .execution_options(synchronize_session=False)
            )
            if written.rowcount != 1:
                db.rollback()
                return None
            db.commit()
            return expected_revision + 1

        if expected_revision != 0:
            return None
        now = _now()
        db.add(
            TradeDraft(
                user_id=owner,
                payload_json=json.dumps(dict(payload)),
                revision=1,
                retired_at=None,
                created_at=now,
                updated_at=now,
            )
        )
        try:
            db.commit()
        except IntegrityError:
            # A concurrent first save or create tombstone won the unique row.
            db.rollback()
            return None
        return 1
    finally:
        db.close()


def save_autofill_suggestions(
    user_id: int,
    suggestions: dict,
    *,
    screenshot_id: int,
    job_id: int,
) -> bool:
    """Store worker output only when it is not older than what is present.

    The row lock makes the compare-and-write one transaction on PostgreSQL.
    Job ids are monotonic enqueue order, so an older provider call finishing
    late cannot replace a newer request's readings.
    """
    owner = require_user_id(user_id)
    db = SessionLocal()
    try:
        row = (
            db.query(TradeDraft)
            .filter(TradeDraft.user_id == owner)
            .with_for_update()
            .first()
        )
        now = _now()
        if row is None:
            payload = {}
            row = TradeDraft(
                user_id=owner,
                payload_json="{}",
                revision=0,
                retired_at=None,
                created_at=now,
                updated_at=now,
            )
            db.add(row)
        else:
            payload = json.loads(row.payload_json)

        stored_job = payload.get("ai_suggestions_job_id")
        if isinstance(stored_job, int) and stored_job > int(job_id):
            db.rollback()
            return False

        payload["ai_suggestions"] = dict(suggestions)
        payload["ai_suggestions_screenshot_id"] = int(screenshot_id)
        payload["ai_suggestions_job_id"] = int(job_id)
        row.payload_json = json.dumps(payload)
        row.revision = int(row.revision) + 1
        row.updated_at = now
        db.commit()
        return True
    except IntegrityError:
        db.rollback()
        # `_clear_draft` normally guarantees a row before autofill can run.
        # A concurrent first writer is safe to retry once through the same
        # locked path rather than losing already-paid output.
        return save_autofill_suggestions(
            owner,
            suggestions,
            screenshot_id=screenshot_id,
            job_id=job_id,
        )
    finally:
        db.close()


def retire_draft(user_id: int) -> int:
    """Make the current revision terminal, retaining an owner tombstone.

    Deleting the row lets a PUT which began before create insert it again
    afterwards.  A tombstone increments the revision instead: every old PUT
    is now a conditional-write conflict, while the next New Trade GET receives
    the new revision and can deliberately reactivate the row.
    """
    owner = require_user_id(user_id)
    db = SessionLocal()
    try:
        now = _now()
        written = db.execute(
            update(TradeDraft)
            .where(TradeDraft.user_id == owner)
            .values(
                payload_json="{}",
                revision=TradeDraft.revision + 1,
                retired_at=now,
                updated_at=now,
            )
            .execution_options(synchronize_session=False)
        )
        if written.rowcount == 1:
            db.commit()
        else:
            db.add(
                TradeDraft(
                    user_id=owner,
                    payload_json="{}",
                    revision=1,
                    retired_at=now,
                    created_at=now,
                    updated_at=now,
                )
            )
            try:
                db.commit()
            except IntegrityError:
                # A concurrent first PUT inserted after our UPDATE observed no
                # row.  Retire that winner before returning from create.
                db.rollback()
                written = db.execute(
                    update(TradeDraft)
                    .where(TradeDraft.user_id == owner)
                    .values(
                        payload_json="{}",
                        revision=TradeDraft.revision + 1,
                        retired_at=now,
                        updated_at=now,
                    )
                    .execution_options(synchronize_session=False)
                )
                if written.rowcount != 1:
                    db.rollback()
                    raise RuntimeError("could not retire draft")
                db.commit()
        revision = (
            db.query(TradeDraft.revision).filter(TradeDraft.user_id == owner).scalar()
        )
        return int(revision)
    finally:
        db.close()


def delete_draft(user_id: int) -> None:
    """Physically remove an owner's draft; a no-op when they have none.

    Completed trades use `retire_draft`, not this helper: retaining a revision
    tombstone is what rejects a PUT that began before create. Physical removal
    remains useful for maintenance/tests and must stay owner-scoped.
    """
    owner = require_user_id(user_id)
    db = SessionLocal()
    try:
        db.query(TradeDraft).filter(TradeDraft.user_id == owner).delete()
        db.commit()
    finally:
        db.close()
