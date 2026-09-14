"""Deleting trades removes the reviews and review jobs made from them (R8, C5)."""

import datetime as dt

import pytest

from src.tradelens.api.storage import ObjectCleanup
from src.tradelens.db.models import AIJob, DailyDebrief, Trade, WeeklyReview
from src.tradelens.db.session import SessionLocal
from src.tradelens.services import daily_debriefs, data_deletion, weekly

FP = "f" * 64


def _clean(monkeypatch, failed=()):
    monkeypatch.setattr(
        data_deletion.storage,
        "delete_trade_objects",
        lambda u, t: ObjectCleanup(deleted=[], failed=list(failed), skipped=[]),
    )


def _trade(owner, *, is_sample=0):
    db = SessionLocal()
    try:
        row = Trade(
            user_id=owner,
            asset="NQ",
            direction="Long",
            result="Win",
            trade_date="2026-09-08",
            is_sample=is_sample,
        )
        db.add(row)
        db.commit()
        return row.id
    finally:
        db.close()


def _seed(owner, *, is_sample=0):
    now = dt.datetime.now(dt.timezone.utc)
    trade_id = _trade(owner, is_sample=is_sample)
    db = SessionLocal()
    try:
        db.add(WeeklyReview(user_id=owner, week_start="2026-09-07", content_md="x"))
        db.add(
            DailyDebrief(
                user_id=owner,
                day="2026-09-08",
                input_fingerprint=FP,
                content_md="x",
                stats_json="{}",
                reviewed_trades=1,
                created_at=now,
                updated_at=now,
            )
        )
        for kind in (
            "weekly_recap",
            "daily_debrief",
            "trade_summary",
            "trade_analysis",
        ):
            db.add(
                AIJob(
                    user_id=owner,
                    kind=kind,
                    idempotency_key=kind,
                    payload="{}",
                    created_at=now,
                )
            )
        db.commit()
    finally:
        db.close()
    return trade_id


def _counts(owner):
    db = SessionLocal()
    try:
        return (
            db.query(WeeklyReview).filter(WeeklyReview.user_id == owner).count(),
            db.query(DailyDebrief).filter(DailyDebrief.user_id == owner).count(),
            sorted(k for (k,) in db.query(AIJob.kind).filter(AIJob.user_id == owner)),
        )
    finally:
        db.close()


ALL_KINDS = ["daily_debrief", "trade_analysis", "trade_summary", "weekly_recap"]


def test_derived_job_kinds_are_named_once():
    assert data_deletion.DERIVED_JOB_KINDS == (
        "trade_summary",
        "weekly_recap",
        "daily_debrief",
    )


def test_delete_all_trades_removes_reviews_and_review_jobs_for_that_owner_only(
    two_users, monkeypatch
):
    a, b = two_users
    _seed(a)
    _seed(b)
    _clean(monkeypatch)
    assert data_deletion.delete_all_trades_and_objects(a).blocked is False
    assert _counts(a) == (0, 0, ["trade_analysis"])
    assert _counts(b) == (1, 1, ALL_KINDS)


def test_a_blocked_deletion_keeps_every_review(two_users, monkeypatch):
    a, _ = two_users
    _seed(a)
    _clean(monkeypatch, failed=["k"])
    assert data_deletion.delete_all_trades_and_objects(a).blocked is True
    assert _counts(a) == (1, 1, ALL_KINDS)


def test_sample_deletion_removes_reviews_and_review_jobs(two_users, monkeypatch):
    a, b = two_users
    _seed(a, is_sample=1)
    _seed(b, is_sample=1)
    _clean(monkeypatch)
    outcome = data_deletion.delete_sample_trades_and_objects(a)
    assert outcome.blocked is False and outcome.deleted == 1
    assert _counts(a) == (0, 0, ["trade_analysis"])
    assert _counts(b) == (1, 1, ALL_KINDS)


def test_account_deletion_removes_reviews_and_every_job(two_users, monkeypatch):
    a, b = two_users
    _seed(a)
    _seed(b)
    _clean(monkeypatch)
    assert data_deletion.delete_account_and_objects(a).blocked is False
    assert _counts(a) == (0, 0, [])
    assert _counts(b) == (1, 1, ALL_KINDS)


def _save_both(owner, trade_id):
    weekly.save_weekly_review_from_sources(
        user_id=owner,
        review={"week_start": "2026-09-07", "content_md": "### What Worked\nx"},
        source_trade_ids=[trade_id],
        input_fingerprint=FP,
        job_id=None,
        verify=lambda db: True,
    )
    daily_debriefs.save_daily_debrief(
        user_id=owner,
        day="2026-09-08",
        input_fingerprint=FP,
        job_id=None,
        result={"content_md": "### Session Summary\nx", "reviewed_trades": 1},
        source_trade_ids=[trade_id],
        verify=lambda db: True,
    )


def test_save_wins_then_delete_all_removes_the_saved_reviews(two_users, monkeypatch):
    a, _ = two_users
    trade_id = _trade(a)
    _save_both(a, trade_id)
    assert _counts(a)[:2] == (1, 1)
    _clean(monkeypatch)
    assert data_deletion.delete_all_trades_and_objects(a).blocked is False
    assert _counts(a)[:2] == (0, 0)


def test_delete_all_wins_then_a_save_writes_nothing(two_users, monkeypatch):
    a, _ = two_users
    trade_id = _trade(a)
    _clean(monkeypatch)
    assert data_deletion.delete_all_trades_and_objects(a).blocked is False
    with pytest.raises(daily_debriefs.ReviewSourceGone):
        weekly.save_weekly_review_from_sources(
            user_id=a,
            review={"week_start": "2026-09-07", "content_md": "### What Worked\nx"},
            source_trade_ids=[trade_id],
            input_fingerprint=FP,
            job_id=1,
            verify=lambda db: True,
        )
    with pytest.raises(daily_debriefs.ReviewSourceGone):
        daily_debriefs.save_daily_debrief(
            user_id=a,
            day="2026-09-08",
            input_fingerprint=FP,
            job_id=2,
            result={"content_md": "### Session Summary\nx", "reviewed_trades": 1},
            source_trade_ids=[trade_id],
            verify=lambda db: True,
        )
    assert _counts(a) == (0, 0, [])
