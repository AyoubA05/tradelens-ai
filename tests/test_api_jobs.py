import pytest
import logging
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from src.tradelens.api import jobs
from src.tradelens.db.models import AIJob
from src.tradelens.db.session import SessionLocal


def test_enqueue_returns_the_new_job_id(two_users):
    a, _ = two_users
    job_id, created = jobs.enqueue(a, "grading", "k1", {"trade_id": 1})
    assert created is True
    assert job_id > 0


def test_the_same_key_returns_the_existing_job_without_a_second_row(two_users):
    """The double-submit control. A repeated request must cost nothing."""
    a, _ = two_users
    first, created_first = jobs.enqueue(a, "grading", "same", {"trade_id": 1})
    second, created_second = jobs.enqueue(a, "grading", "same", {"trade_id": 1})

    assert first == second
    assert created_second is False

    db = SessionLocal()
    try:
        assert db.query(AIJob).filter(AIJob.user_id == a).count() == 1
    finally:
        db.close()


def test_concurrent_duplicate_enqueues_create_exactly_one_job(two_users):
    a, _ = two_users
    gate = Barrier(2)

    def submit():
        gate.wait()
        return jobs.enqueue(a, "grading", "concurrent-key", {"trade_id": 1})

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: submit(), range(2)))

    assert len({job_id for job_id, _ in results}) == 1
    assert sorted(created for _, created in results) == [False, True]
    db = SessionLocal()
    try:
        assert db.query(AIJob).filter(AIJob.user_id == a).count() == 1
    finally:
        db.close()


def test_one_users_key_does_not_block_another(two_users):
    a, b = two_users
    _, created_a = jobs.enqueue(a, "grading", "shared", {})
    _, created_b = jobs.enqueue(b, "grading", "shared", {})
    assert created_a and created_b


def test_enqueue_requires_a_real_owner():
    with pytest.raises(ValueError):
        jobs.enqueue(None, "grading", "k", {})


def test_claim_marks_the_job_running_and_counts_the_attempt(two_users):
    a, _ = two_users
    job_id, _ = jobs.enqueue(a, "grading", "k2", {})

    claimed = jobs.claim_next()

    assert claimed.id == job_id
    assert claimed.status == "running"
    assert claimed.attempts == 1


def test_a_claimed_job_is_not_claimed_twice(two_users):
    """Two workers must not both pay for the same Anthropic call."""
    a, _ = two_users
    jobs.enqueue(a, "grading", "k3", {})
    assert jobs.claim_next() is not None
    assert jobs.claim_next() is None


def test_concurrent_claims_cannot_both_take_the_same_job(two_users):
    a, _ = two_users
    job_id, _ = jobs.enqueue(a, "grading", "claim-race", {})
    gate = Barrier(2)

    def claim():
        gate.wait()
        row = jobs.claim_next()
        return None if row is None else row.id

    with ThreadPoolExecutor(max_workers=2) as pool:
        claimed = list(pool.map(lambda _: claim(), range(2)))

    assert claimed.count(job_id) == 1
    assert claimed.count(None) == 1
    db = SessionLocal()
    try:
        row = db.get(AIJob, job_id)
        assert row.status == "running"
        assert row.attempts == 1
    finally:
        db.close()


def test_complete_records_where_the_result_landed(two_users):
    a, _ = two_users
    job_id, _ = jobs.enqueue(a, "grading", "k4", {})
    jobs.claim_next()
    jobs.complete(job_id, "aianalysis:42")

    db = SessionLocal()
    try:
        job = db.get(AIJob, job_id)
        assert job.status == "succeeded"
        assert job.result_ref == "aianalysis:42"
        assert job.finished_at is not None
    finally:
        db.close()


def test_failure_stores_a_message_safe_to_show_a_user(two_users):
    a, _ = two_users
    job_id, _ = jobs.enqueue(a, "grading", "k5", {})
    jobs.claim_next()
    jobs.fail(job_id, "The review could not be generated. Try again.")

    db = SessionLocal()
    try:
        job = db.get(AIJob, job_id)
        assert job.status == "failed"
        assert "Traceback" not in (job.error or "")
    finally:
        db.close()


def test_run_once_dispatches_to_the_handler_for_the_job_kind(two_users):
    a, _ = two_users
    jobs.enqueue(a, "grading", "k6", {"trade_id": 7})
    seen = {}

    def handler(user_id, payload):
        seen["user_id"] = user_id
        seen["payload"] = payload
        return "aianalysis:7"

    assert jobs.run_once({"grading": handler}) is True
    assert seen == {"user_id": a, "payload": {"trade_id": 7}}


def test_run_once_returns_false_when_the_queue_is_empty(two_users):
    """Takes the fixture purely for its schema.

    Without it this reached whatever database happened to exist — a fully
    migrated one on a developer machine, and none at all in CI.
    """
    assert jobs.run_once({}) is False


def test_a_handler_that_raises_fails_without_leaking_detail_to_db_or_logs(
    two_users, caplog
):
    a, _ = two_users
    jobs.enqueue(a, "grading", "k7", {})

    def explode(user_id, payload):
        raise RuntimeError("anthropic said something with a key in it")

    with caplog.at_level(logging.ERROR, logger="src.tradelens.api.jobs"):
        jobs.run_once({"grading": explode})

    db = SessionLocal()
    try:
        job = db.query(AIJob).filter(AIJob.idempotency_key == "k7").one()
        assert job.status == "failed"
        assert "anthropic said" not in (job.error or "")
    finally:
        db.close()
    assert "anthropic said" not in caplog.text
