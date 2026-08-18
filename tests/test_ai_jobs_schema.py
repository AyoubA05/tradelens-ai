import pytest
from sqlalchemy.exc import IntegrityError

from src.tradelens.db.models import AIJob
from src.tradelens.db.session import SessionLocal


def test_the_same_idempotency_key_cannot_be_enqueued_twice(two_users):
    """The control that stops a double-submitted screenshot being paid for twice."""
    a, _ = two_users
    db = SessionLocal()
    try:
        db.add(AIJob(user_id=a, kind="screenshot_analysis", idempotency_key="k1"))
        db.commit()
        db.add(AIJob(user_id=a, kind="screenshot_analysis", idempotency_key="k1"))
        with pytest.raises(IntegrityError):
            db.commit()
    finally:
        db.rollback()
        db.close()


def test_two_users_may_reuse_the_same_key(two_users):
    """The key is unique per owner, not globally: one trader's key must not
    block another's."""
    a, b = two_users
    db = SessionLocal()
    try:
        db.add(AIJob(user_id=a, kind="grading", idempotency_key="same"))
        db.add(AIJob(user_id=b, kind="grading", idempotency_key="same"))
        db.commit()
    finally:
        db.close()


def test_a_new_job_starts_queued(two_users):
    a, _ = two_users
    db = SessionLocal()
    try:
        job = AIJob(user_id=a, kind="weekly_review", idempotency_key="k2")
        db.add(job)
        db.commit()
        db.refresh(job)
        assert job.status == "queued"
        assert job.attempts == 0
    finally:
        db.close()
