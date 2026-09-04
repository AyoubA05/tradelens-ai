"""The Phase 5 worker handlers, tested directly.

`jobs.run_once` hands a handler only `(user_id, payload)` — never the job
row — so each Phase 5 handler has to recover its own job id before it can
order a write by it. That recovery is a tenant boundary: it looks a job up
by a key the payload carries, and it must never resolve to a row belonging
to someone else.

Tested here rather than through a route because the handler is what runs in
production. A mutation that hardcoded the owner in the lookup survived the
entire suite before this file existed.
"""

import datetime as _dt

import pytest

from src.tradelens.api import jobs, worker
from src.tradelens.services.trade_analysis import ANALYSIS_JOB_KIND


def _enqueue(user_id: int, key: str) -> int:
    job_id, _created = jobs.enqueue_with_limit(
        user_id,
        ANALYSIS_JOB_KIND,
        key,
        {"trade_id": 1, "screenshot_id": 1, "key": key},
        since=_dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(hours=24),
        limit=20,
    )
    assert job_id is not None
    return int(job_id)


def test_a_handler_recovers_the_id_of_the_job_it_is_running(two_users):
    owner, _other = two_users
    job_id = _enqueue(owner, "trade_analysis:abc")
    resolved = worker._phase5_job_id(
        owner, ANALYSIS_JOB_KIND, {"key": "trade_analysis:abc"}
    )
    assert resolved == job_id


def test_a_handler_never_resolves_another_owner_s_job(two_users):
    """The payload names a key, and a key alone is not authority.

    Both traders can hold the same idempotency key — it is a digest of their
    own inputs, and `ai_jobs` is unique on `(user_id, idempotency_key)`, so
    collisions across accounts are ordinary. A lookup that dropped its owner
    scope would let one trader's worker run order a write against the other's
    job id.
    """
    owner, other = two_users
    owner_job = _enqueue(owner, "trade_analysis:same")
    other_job = _enqueue(other, "trade_analysis:same")
    assert owner_job != other_job

    assert (
        worker._phase5_job_id(other, ANALYSIS_JOB_KIND, {"key": "trade_analysis:same"})
        == other_job
    )
    assert (
        worker._phase5_job_id(owner, ANALYSIS_JOB_KIND, {"key": "trade_analysis:same"})
        == owner_job
    )


def test_a_key_with_no_job_for_this_owner_refuses(two_users):
    """Failing loudly beats ordering a write by a guessed id."""
    owner, other = two_users
    _enqueue(other, "trade_analysis:only-theirs")
    with pytest.raises(RuntimeError):
        worker._phase5_job_id(
            owner, ANALYSIS_JOB_KIND, {"key": "trade_analysis:only-theirs"}
        )


def test_a_handler_will_not_read_a_job_of_another_kind(two_users):
    """Kind is part of the lookup, so a summary cannot be run as an analysis."""
    owner, _other = two_users
    _enqueue(owner, "trade_analysis:kinded")
    with pytest.raises(RuntimeError):
        worker._phase5_job_id(owner, "trade_summary", {"key": "trade_analysis:kinded"})


def test_the_analysis_handler_passes_the_resolved_job_id_to_the_write(
    two_users, monkeypatch
):
    """The whole point of the lookup: the write is ordered by THIS job's id."""
    owner, _other = two_users
    job_id = _enqueue(owner, "trade_analysis:passed")
    seen = {}

    def fake_run(user_id, trade_id, screenshot_id, *, job_id, on_usage):
        seen["job_id"] = job_id
        seen["user_id"] = user_id

        class _Outcome:
            written = True

        return _Outcome()

    monkeypatch.setattr(worker, "run_analysis", fake_run)
    worker._trade_analysis_handler(
        owner, {"trade_id": 1, "screenshot_id": 1, "key": "trade_analysis:passed"}
    )
    assert seen["job_id"] == job_id
    assert seen["user_id"] == owner
