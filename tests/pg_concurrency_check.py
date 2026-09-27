"""Subprocess scenarios for live-PostgreSQL concurrency (production gate 1).

Run by tests/test_postgres_concurrency.py in a child process so DATABASE_URL is
set before any src.tradelens module is imported (the same isolation reason as
tests/app_boot_check.py). Prints one JSON line with what was observed; the test
decides what is acceptable. Not collected by pytest.

Usage: DATABASE_URL=<disposable> python pg_concurrency_check.py <scenario>
"""

import json
import sys
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.tradelens.db.models import (  # noqa: E402
    AIJob,
    Trade,
    TradeSummaryResult,
    User,
    WeeklyReview,
)
from src.tradelens.db.session import SessionLocal  # noqa: E402

WEEK = "2026-09-07"  # a Monday
DAYS = ("2026-09-07", "2026-09-08", "2026-09-09")


def _make_owner() -> tuple[int, list[int]]:
    db = SessionLocal()
    try:
        user = User(username=f"gate1-{uuid.uuid4().hex[:12]}", password_hash="x")
        db.add(user)
        db.flush()
        trades = [
            Trade(
                trade_date=day,
                asset="NQ",
                direction="Long",
                result="Win",
                pnl=100.0,
                user_id=user.id,
            )
            for day in DAYS
        ]
        db.add_all(trades)
        db.commit()
        return int(user.id), [int(t.id) for t in trades]
    finally:
        db.close()


def _count(model, *criteria) -> int:
    db = SessionLocal()
    try:
        return db.query(model).filter(*criteria).count()
    finally:
        db.close()


def _run_all(targets):
    """Start every callable at the same instant; return (results, errors)."""
    barrier = threading.Barrier(len(targets))
    results, errors = [None] * len(targets), []

    def runner(i, fn):
        barrier.wait()
        try:
            results[i] = fn()
        except Exception as exc:  # noqa: BLE001 — the scenario reports it
            errors.append(type(exc).__name__)

    threads = [
        threading.Thread(target=runner, args=(i, fn)) for i, fn in enumerate(targets)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join(120)
    return results, errors


def weekly_unique() -> dict:
    """Twelve concurrent recap saves for one (owner, week), both save paths."""
    from src.tradelens.services import weekly

    uid, ids = _make_owner()
    review = {"week_start": WEEK, "content_md": "recap", "stats": {}, "cost_usd": 0.0}

    def legacy():
        return weekly.save_weekly_review(review, uid, overwrite=True)["id"]

    def job():
        return weekly.save_weekly_review_from_sources(
            user_id=uid,
            review=review,
            source_trade_ids=ids,
            input_fingerprint="f" * 64,
            job_id=None,
            verify=lambda db: True,
        )

    _, errors = _run_all([legacy, job] * 6)
    rows = _count(
        WeeklyReview, WeeklyReview.user_id == uid, WeeklyReview.week_start == WEEK
    )
    return {"rows": rows, "errors": errors}


def enqueue_limit() -> dict:
    """Twenty distinct keys against a limit of five, then ten copies of one key."""
    from src.tradelens.api import jobs

    uid, _ = _make_owner()
    since = datetime.now(timezone.utc) - timedelta(hours=1)

    def distinct(i):
        return lambda: jobs.enqueue_with_limit(
            uid, "gate1_kind", f"key-{i}", {}, since=since, limit=5
        )

    results, errors = _run_all([distinct(i) for i in range(20)])
    created = sum(1 for r in results if r and r[1])
    refused = sum(1 for r in results if r == (None, False))

    def same():
        return jobs.enqueue_with_limit(
            uid, "gate1_same", "one-key", {}, since=since, limit=5
        )

    same_results, same_errors = _run_all([same] * 10)
    return {
        "created": created,
        "refused": refused,
        "rows": _count(AIJob, AIJob.user_id == uid, AIJob.kind == "gate1_kind"),
        "errors": errors,
        "same_created": sum(1 for r in same_results if r and r[1]),
        "same_ids": len({r[0] for r in same_results if r}),
        "same_rows": _count(AIJob, AIJob.user_id == uid, AIJob.kind == "gate1_same"),
        "same_errors": same_errors,
    }


def _delete_race(save_first: bool, hold: float = 3.0) -> dict:
    """A running recap save and an account deletion, in either order.

    `hold` is how long the save keeps its source locks before inserting. A
    long hold lets Postgres's one-second deadlock check pass before the cycle
    exists; a sub-second hold — a real worker's timing — does not.
    """
    from src.tradelens.services import data_deletion, weekly

    uid, ids = _make_owner()
    review = {"week_start": WEEK, "content_md": "recap", "stats": {}, "cost_usd": 0.0}
    locked = threading.Event()
    outcome = {"save_error": None, "delete_error": None, "delete_seconds": None}

    def slow_verify(db):
        locked.set()
        time.sleep(hold)
        return True

    def save():
        try:
            weekly.save_weekly_review_from_sources(
                user_id=uid,
                review=review,
                source_trade_ids=ids,
                input_fingerprint="f" * 64,
                job_id=None,
                verify=slow_verify,
            )
        except Exception as exc:  # noqa: BLE001
            outcome["save_error"] = type(exc).__name__

    def delete():
        start = time.monotonic()
        try:
            result = data_deletion.delete_account_and_objects(uid)
            outcome["deleted"] = result.deleted
        except Exception as exc:  # noqa: BLE001
            outcome["delete_error"] = type(exc).__name__
        outcome["delete_seconds"] = round(time.monotonic() - start, 2)

    if save_first:
        s = threading.Thread(target=save)
        s.start()
        locked.wait(30)
        d = threading.Thread(target=delete)
        d.start()
        s.join(120)
        d.join(120)
    else:
        delete()
        save()
    outcome["user_rows"] = _count(User, User.id == uid)
    outcome["review_rows"] = _count(WeeklyReview, WeeklyReview.user_id == uid)
    return outcome


def delete_while_saving() -> dict:
    return _delete_race(save_first=True)


def delete_during_fast_save() -> dict:
    return _delete_race(save_first=True, hold=0.3)


def delete_during_fast_trade_summary_save() -> dict:
    """The same race through the trade-summary writer, which has no verify
    hook: the hold is injected just before its owner-referencing insert."""
    from src.tradelens.services import data_deletion, trade_summary

    uid, ids = _make_owner()
    locked = threading.Event()
    real_row = trade_summary.TradeSummaryResult
    outcome = {"save_error": None, "delete_error": None}

    def slow_row(**kwargs):
        locked.set()
        time.sleep(0.3)
        return real_row(**kwargs)

    trade_summary.TradeSummaryResult = slow_row

    def save():
        try:
            trade_summary.save_trade_summary_result(
                user_id=uid,
                summary_key="k" * 64,
                filters={},
                result={"content_md": "summary", "reviewed_trades": len(ids)},
                source_trade_ids=ids,
            )
        except Exception as exc:  # noqa: BLE001
            outcome["save_error"] = type(exc).__name__

    def delete():
        try:
            data_deletion.delete_account_and_objects(uid)
        except Exception as exc:  # noqa: BLE001
            outcome["delete_error"] = type(exc).__name__

    s_thread = threading.Thread(target=save)
    s_thread.start()
    locked.wait(30)
    d_thread = threading.Thread(target=delete)
    d_thread.start()
    s_thread.join(120)
    d_thread.join(120)
    trade_summary.TradeSummaryResult = real_row
    outcome["user_rows"] = _count(User, User.id == uid)
    outcome["summary_rows"] = _count(
        TradeSummaryResult, TradeSummaryResult.user_id == uid
    )
    return outcome


def save_after_delete() -> dict:
    return _delete_race(save_first=False)


def source_lock_blocks_writers() -> dict:
    """While a save holds its sources `FOR UPDATE`, a trade edit must wait."""
    from src.tradelens.services.daily_debriefs import lock_and_verify_sources

    uid, ids = _make_owner()
    locked = threading.Event()
    observed = {}

    def holder():
        db = SessionLocal()
        try:

            def verify(_db):
                locked.set()
                time.sleep(2)
                return True

            lock_and_verify_sources(db, uid, ids, verify)
            db.commit()
        finally:
            db.close()

    def writer():
        locked.wait(30)
        start = time.monotonic()
        db = SessionLocal()
        try:
            db.query(Trade).filter(Trade.id == ids[0]).update({"pnl": 1.0})
            db.commit()
        finally:
            db.close()
        observed["writer_waited_seconds"] = round(time.monotonic() - start, 2)

    h, w = threading.Thread(target=holder), threading.Thread(target=writer)
    h.start()
    w.start()
    h.join(60)
    w.join(60)
    return observed


SCENARIOS = {
    fn.__name__: fn
    for fn in (
        weekly_unique,
        enqueue_limit,
        delete_while_saving,
        delete_during_fast_save,
        delete_during_fast_trade_summary_save,
        save_after_delete,
        source_lock_blocks_writers,
    )
}

if __name__ == "__main__":
    print(json.dumps(SCENARIOS[sys.argv[1]]()))
