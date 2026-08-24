"""Enqueue, claim and complete asynchronous AI work.

Two properties matter more than throughput:

* **An enqueue is idempotent per owner.** A repeated request returns the
  existing job. Without it a double-clicked button is a second Anthropic bill.
* **A claim is exclusive.** Two workers must never run the same job, for the
  same reason.

Both rest on the `(user_id, idempotency_key)` constraint and a conditional
UPDATE, not on application-level checking — a read-then-write would race.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Callable, Dict, Optional, Tuple

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from src.tradelens.db.models import AIJob
from src.tradelens.db.session import SessionLocal
from src.tradelens.services.corrections import corrections_scope
from src.tradelens.services.ownership import require_user_id

_log = logging.getLogger(__name__)

_GENERIC_FAILURE = "This could not be generated. Please try again."


def _now() -> datetime:
    return datetime.now(timezone.utc)


def enqueue(
    user_id: int, kind: str, idempotency_key: str, payload: dict
) -> Tuple[int, bool]:
    """Queue a job. Returns `(job_id, was_created)`.

    The uniqueness violation is caught rather than pre-checked: between a
    SELECT and an INSERT another request can land, and the constraint is the
    only thing that cannot be raced.
    """
    owner = require_user_id(user_id)
    db = SessionLocal()
    try:
        job = AIJob(
            user_id=owner,
            kind=kind,
            idempotency_key=idempotency_key,
            payload=json.dumps(payload),
            status="queued",
            created_at=_now(),
        )
        db.add(job)
        db.commit()
        return int(job.id), True
    except IntegrityError:
        db.rollback()
        existing = (
            db.query(AIJob)
            .filter(AIJob.user_id == owner, AIJob.idempotency_key == idempotency_key)
            .one()
        )
        return int(existing.id), False
    finally:
        db.close()


def get_owned_job(job_id: int, user_id: int) -> Optional[AIJob]:
    """Return one job only when it belongs to the authenticated owner."""
    owner = require_user_id(user_id)
    db = SessionLocal()
    try:
        return (
            db.query(AIJob).filter(AIJob.id == job_id, AIJob.user_id == owner).first()
        )
    finally:
        db.close()


def claim_next() -> Optional[AIJob]:
    """Atomically take the oldest queued job, or return None.

    The UPDATE is conditional on the row still being queued, so two workers
    racing produce one winner and one None — never two runs of one job.
    """
    db = SessionLocal()
    try:
        row = (
            db.query(AIJob.id)
            .filter(AIJob.status == "queued")
            .order_by(AIJob.id.asc())
            .first()
        )
        if row is None:
            return None

        claimed = db.execute(
            text(
                "UPDATE ai_jobs SET status = 'running', started_at = :now, "
                "attempts = attempts + 1 WHERE id = :id AND status = 'queued'"
            ),
            {"now": _now(), "id": row[0]},
        )
        db.commit()
        if claimed.rowcount != 1:
            return None
        return db.get(AIJob, row[0])
    finally:
        db.close()


def complete(job_id: int, result_ref: str) -> None:
    _finish(job_id, status="succeeded", result_ref=result_ref, error=None)


def fail(job_id: int, message: str) -> None:
    """Mark a job failed with a message that is safe to show a user."""
    _finish(job_id, status="failed", result_ref=None, error=message)


def _finish(job_id: int, *, status: str, result_ref, error) -> None:
    db = SessionLocal()
    try:
        db.execute(
            text(
                "UPDATE ai_jobs SET status = :s, result_ref = :r, error = :e, "
                "finished_at = :now WHERE id = :id"
            ),
            {"s": status, "r": result_ref, "e": error, "now": _now(), "id": job_id},
        )
        db.commit()
    finally:
        db.close()


def run_once(handlers: Dict[str, Callable[[int, dict], str]]) -> bool:
    """Claim and run one job. Returns whether there was one to run.

    The handler's exception is logged and discarded rather than stored: a
    provider error message can carry a prompt fragment or a key, and this
    column is read by a user.
    """
    job = claim_next()
    if job is None:
        return False

    handler = handlers.get(job.kind)
    if handler is None:
        fail(job.id, _GENERIC_FAILURE)
        _log.error("no handler registered for job kind %r", job.kind)
        return True

    try:
        payload = json.loads(job.payload or "{}")
        with corrections_scope(job.user_id):
            result_ref = handler(job.user_id, payload)
        complete(job.id, result_ref)
    except Exception as exc:  # noqa: BLE001 — message withheld deliberately
        # Provider exceptions can embed request fragments, response bodies, or
        # credentials. Log only the class name; no message and no traceback.
        _log.error("job %s (%r) failed (%s)", job.id, job.kind, type(exc).__name__)
        fail(job.id, _GENERIC_FAILURE)
    return True
