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


# --- the two handlers Group B added -------------------------------------
#
# This file exists because a mutation that hardcoded the owner in the lookup
# once survived the whole suite. Group B added two more handlers without
# extending it, and three mutations against them survived in turn: resolving
# with the wrong KIND, passing a hardcoded job id, and never logging usage.


def _enqueue_kind(user_id: int, kind: str, key: str) -> int:
    job_id, _created = jobs.enqueue_with_limit(
        user_id,
        kind,
        key,
        {"trade_id": 1, "key": key},
        since=_dt.datetime.now(_dt.timezone.utc) - _dt.timedelta(hours=24),
        limit=20,
    )
    assert job_id is not None
    return int(job_id)


class _Written:
    written = True


@pytest.mark.parametrize(
    "handler_name,run_name,kind",
    [
        ("_trade_journal_handler", "run_journal", "trade_journal"),
        ("_trade_grade_handler", "run_grade", "trade_grade"),
    ],
)
def test_a_derived_handler_passes_its_own_resolved_job_id(
    two_users, monkeypatch, handler_name, run_name, kind
):
    """A hardcoded id feeds the ordering guard a lie in production.

    Every Phase 5 write is ordered by job id, so a handler that passes a
    constant makes "newer wins" meaningless while every service-level test
    still passes — they call the run function directly and never go through
    the handler.
    """
    owner, _other = two_users
    key = f"{kind}:resolved"
    job_id = _enqueue_kind(owner, kind, key)
    seen = {}

    def fake_run(user_id, trade_id, *, job_id, on_usage):
        seen["job_id"] = job_id
        seen["user_id"] = user_id
        return _Written()

    monkeypatch.setattr(worker, run_name, fake_run)
    getattr(worker, handler_name)(owner, {"trade_id": 1, "key": key})

    assert seen["job_id"] == job_id
    assert seen["user_id"] == owner


@pytest.mark.parametrize(
    "handler_name,run_name,kind,wrong_kind",
    [
        ("_trade_journal_handler", "run_journal", "trade_journal", "trade_grade"),
        ("_trade_grade_handler", "run_grade", "trade_grade", "trade_journal"),
    ],
)
def test_a_derived_handler_resolves_only_its_own_kind(
    two_users, monkeypatch, handler_name, run_name, kind, wrong_kind
):
    """Two kinds can share a key shape, so the lookup must be kind-scoped.

    Resolving with the wrong kind finds no job and must refuse, rather than
    silently running against a job of another feature.
    """
    owner, _other = two_users
    key = f"{kind}:only"
    _enqueue_kind(owner, wrong_kind, key)

    monkeypatch.setattr(worker, run_name, lambda *a, **k: _Written())
    with pytest.raises(RuntimeError):
        getattr(worker, handler_name)(owner, {"trade_id": 1, "key": key})


@pytest.mark.parametrize(
    "handler_name,run_name,kind,feature",
    [
        ("_trade_journal_handler", "run_journal", "trade_journal", "AI Journal"),
        ("_trade_grade_handler", "run_grade", "trade_grade", "Trade Grading"),
    ],
)
def test_a_derived_handler_logs_usage_under_the_expected_feature(
    two_users, monkeypatch, handler_name, run_name, kind, feature
):
    """The handler is the only place the feature STRING is chosen.

    A no-op callback here loses every journal or grade from the Settings cost
    dashboard while the service-level accounting tests stay green, and a
    renamed string silently splits one feature across two rows.
    """
    owner, _other = two_users
    key = f"{kind}:usage"
    _enqueue_kind(owner, kind, key)
    logged = []

    def fake_run(user_id, trade_id, *, job_id, on_usage):
        on_usage(object())
        return _Written()

    monkeypatch.setattr(worker, run_name, fake_run)
    monkeypatch.setattr(
        worker,
        "log_ai_usage",
        lambda name, usage, user_id: logged.append((name, user_id)),
    )
    getattr(worker, handler_name)(owner, {"trade_id": 1, "key": key})

    assert logged == [(feature, owner)]


@pytest.mark.parametrize(
    "handler_name,run_name,kind",
    [
        ("_trade_journal_handler", "run_journal", "trade_journal"),
        ("_trade_grade_handler", "run_grade", "trade_grade"),
    ],
)
def test_a_derived_handler_never_resolves_another_owner_s_job(
    two_users, monkeypatch, handler_name, run_name, kind
):
    """The tenant boundary this file was written for, on the new handlers."""
    owner, other = two_users
    key = f"{kind}:theirs"
    _enqueue_kind(other, kind, key)

    monkeypatch.setattr(worker, run_name, lambda *a, **k: _Written())
    with pytest.raises(RuntimeError):
        getattr(worker, handler_name)(owner, {"trade_id": 1, "key": key})
