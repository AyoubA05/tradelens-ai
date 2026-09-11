"""The AI Partner turn path (Phase 8, Group B).

B2 — the rate-limit ticket. A Partner turn is a synchronous paid call, so it
takes the same owner-locked limit and duplicate check as queued AI work, but
as a `running` row the worker never claims, and one that carries no text.
"""

from __future__ import annotations

import threading
from datetime import datetime, timedelta, timezone

import pytest

from src.tradelens.api import jobs
from src.tradelens.db.models import AIJob
from src.tradelens.db.session import SessionLocal

KIND = "partner_turn"


def _since():
    return datetime.now(timezone.utc) - timedelta(hours=24)


def _row(job_id):
    db = SessionLocal()
    try:
        return db.query(AIJob).filter(AIJob.id == job_id).one()
    finally:
        db.close()


# ── B2: the ticket ────────────────────────────────────────────────────────


def test_a_running_ticket_is_never_claimed_by_the_worker(two_users):
    owner = two_users[0]
    ticket, created = jobs.enqueue_with_limit(
        owner, KIND, "k" * 64, {}, since=_since(), limit=5, initial_status="running"
    )
    assert created is True
    assert _row(ticket).status == "running"
    assert jobs.claim_next() is None


def test_the_default_is_still_queued_work_the_worker_claims(two_users):
    owner = two_users[0]
    job, created = jobs.enqueue_with_limit(
        owner, "trade_summary", "q" * 64, {}, since=_since(), limit=5
    )
    assert created is True and _row(job).status == "queued"
    claimed = jobs.claim_next()
    assert claimed is not None and claimed.id == job


@pytest.mark.parametrize("status", ["succeeded", "failed", "", "RUNNING", None])
def test_any_other_initial_status_is_refused(two_users, status):
    with pytest.raises(ValueError):
        jobs.enqueue_with_limit(
            two_users[0],
            KIND,
            "s" * 64,
            {},
            since=_since(),
            limit=5,
            initial_status=status,
        )


def test_tickets_count_toward_the_limit(two_users):
    owner = two_users[0]
    for i in range(2):
        _id, created = jobs.enqueue_with_limit(
            owner,
            KIND,
            "%064d" % i,
            {},
            since=_since(),
            limit=2,
            initial_status="running",
        )
        assert created
    over = jobs.enqueue_with_limit(
        owner,
        KIND,
        "%064d" % 9,
        {},
        since=_since(),
        limit=2,
        initial_status="running",
    )
    assert over == (None, False)


def test_a_reused_key_returns_the_existing_ticket_not_a_new_one(two_users):
    owner = two_users[0]
    first = jobs.enqueue_with_limit(
        owner, KIND, "d" * 64, {}, since=_since(), limit=5, initial_status="running"
    )
    again = jobs.enqueue_with_limit(
        owner, KIND, "d" * 64, {}, since=_since(), limit=5, initial_status="running"
    )
    assert first[1] is True
    assert again == (first[0], False)


def test_two_concurrent_requests_for_the_last_slot_leave_exactly_one_ticket(two_users):
    owner = two_users[0]
    barrier = threading.Barrier(2, timeout=5)
    results = []

    def take(key):
        barrier.wait()
        results.append(
            jobs.enqueue_with_limit(
                owner,
                KIND,
                key,
                {},
                since=_since(),
                limit=1,
                initial_status="running",
            )
        )

    threads = [threading.Thread(target=take, args=(k * 64,)) for k in ("a", "b")]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    created = [r for r in results if r[1] is True]
    refused = [r for r in results if r == (None, False)]
    assert len(created) == 1 and len(refused) == 1
