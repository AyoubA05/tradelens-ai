import datetime as dt

import pytest

from src.tradelens.db.models import DailyDebrief, Trade, WeeklyReview
from src.tradelens.db.session import SessionLocal
from src.tradelens.services import daily_debriefs, weekly

RESULT = {
    "content_md": "### Session Summary\nok",
    "stats": {"trades": 1},
    "reviewed_trades": 1,
}
FP1 = "a" * 64
FP2 = "b" * 64


def _ok(db):
    return True


def _trade(owner, day="2026-09-08"):
    db = SessionLocal()
    try:
        row = Trade(
            user_id=owner, asset="NQ", direction="Long", result="Win", trade_date=day
        )
        db.add(row)
        db.commit()
        return row.id
    finally:
        db.close()


def _delete_trade(trade_id):
    db = SessionLocal()
    try:
        db.query(Trade).filter(Trade.id == trade_id).delete()
        db.commit()
    finally:
        db.close()


def _debrief_rows(owner):
    db = SessionLocal()
    try:
        return db.query(DailyDebrief).filter(DailyDebrief.user_id == owner).all()
    finally:
        db.close()


def _save(owner, trade_ids, **overrides):
    kwargs = dict(
        user_id=owner,
        day="2026-09-08",
        input_fingerprint=FP1,
        job_id=7,
        result=RESULT,
        source_trade_ids=trade_ids,
        verify=_ok,
    )
    kwargs.update(overrides)
    return daily_debriefs.save_daily_debrief(**kwargs)


def test_save_and_read_are_owner_scoped(two_users):
    a, b = two_users
    t = _trade(a)
    rid = _save(a, [t])
    saved = daily_debriefs.get_daily_debrief(user_id=a, day="2026-09-08")
    assert saved["content_md"].startswith("###")
    assert saved["stats"] == {"trades": 1}
    assert saved["reviewed_trades"] == 1
    assert daily_debriefs.get_daily_debrief(user_id=b, day="2026-09-08") is None
    assert daily_debriefs.get_daily_debrief_by_id(rid, a)["id"] == rid
    assert daily_debriefs.get_daily_debrief_by_id(rid, b) is None


def test_save_records_provenance(two_users):
    a, _ = two_users
    t = _trade(a)
    _save(a, [t])
    saved = daily_debriefs.get_daily_debrief(user_id=a, day="2026-09-08")
    assert saved["day"] == "2026-09-08"
    assert saved["input_fingerprint"] == FP1
    assert saved["job_id"] == 7
    assert saved["created_at"] is not None
    assert saved["updated_at"] is not None


def test_regenerate_replaces_the_day_and_keeps_created_at(two_users):
    a, _ = two_users
    t = _trade(a)
    _save(a, [t])
    first = daily_debriefs.get_daily_debrief(user_id=a, day="2026-09-08")
    _save(
        a,
        [t],
        input_fingerprint=FP2,
        job_id=8,
        result={**RESULT, "content_md": "### Session Summary\nnew"},
    )
    assert len(_debrief_rows(a)) == 1
    second = daily_debriefs.get_daily_debrief(user_id=a, day="2026-09-08")
    assert "new" in second["content_md"]
    assert second["input_fingerprint"] == FP2
    assert second["job_id"] == 8
    assert second["created_at"] == first["created_at"]
    assert second["updated_at"] >= first["updated_at"]


def test_a_deleted_source_trade_fails_closed(two_users):
    a, _ = two_users
    t = _trade(a)
    _delete_trade(t)
    with pytest.raises(daily_debriefs.ReviewSourceGone):
        _save(a, [t])
    assert daily_debriefs.get_daily_debrief(user_id=a, day="2026-09-08") is None


def test_no_sources_fails_closed(two_users):
    a, _ = two_users
    with pytest.raises(daily_debriefs.ReviewSourceGone):
        _save(a, [])
    assert _debrief_rows(a) == []


def test_another_owners_trade_is_not_a_source(two_users):
    a, b = two_users
    theirs = _trade(b)
    with pytest.raises(daily_debriefs.ReviewSourceGone):
        _save(a, [theirs])
    assert _debrief_rows(a) == []


def test_verifier_runs_inside_the_locked_transaction_before_the_write(two_users):
    a, _ = two_users
    t = _trade(a)
    seen = []

    def verify(db):
        # The session it receives can read the locked sources; nothing is written yet.
        seen.append(db.query(Trade.id).filter(Trade.id == t).scalar())
        seen.append(db.query(DailyDebrief).count())
        return True

    _save(a, [t], verify=verify)
    assert seen == [t, 0]
    assert len(_debrief_rows(a)) == 1


def test_a_failing_verifier_writes_nothing(two_users):
    a, _ = two_users
    t = _trade(a)
    with pytest.raises(daily_debriefs.ReviewSourceChanged):
        _save(a, [t], verify=lambda db: False)
    assert _debrief_rows(a) == []


def test_a_failing_verifier_keeps_the_existing_note(two_users):
    a, _ = two_users
    t = _trade(a)
    _save(a, [t])
    with pytest.raises(daily_debriefs.ReviewSourceChanged):
        _save(
            a,
            [t],
            input_fingerprint=FP2,
            result={**RESULT, "content_md": "### Session Summary\nnew"},
            verify=lambda db: False,
        )
    kept = daily_debriefs.get_daily_debrief(user_id=a, day="2026-09-08")
    assert kept["content_md"].endswith("ok")
    assert kept["input_fingerprint"] == FP1


def test_verifier_is_not_called_when_a_source_is_gone(two_users):
    a, _ = two_users
    t = _trade(a)
    _delete_trade(t)
    calls = []
    with pytest.raises(daily_debriefs.ReviewSourceGone):
        _save(a, [t], verify=lambda db: calls.append(db) or True)
    assert calls == []


def test_source_changed_is_a_source_gone():
    assert issubclass(
        daily_debriefs.ReviewSourceChanged, daily_debriefs.ReviewSourceGone
    )


def _review(content="### What Worked\nx"):
    return {
        "week_start": "2026-09-07",
        "content_md": content,
        "thinking_summary": None,
        "stats": {"trades": 1},
        "cost_usd": 0.0,
    }


def _weekly_row(owner):
    db = SessionLocal()
    try:
        return (
            db.query(WeeklyReview)
            .filter(WeeklyReview.user_id == owner)
            .order_by(WeeklyReview.id)
            .all()
        )
    finally:
        db.close()


def test_weekly_save_from_sources_locks_overwrites_and_records_provenance(two_users):
    a, _ = two_users
    t = _trade(a)
    first = weekly.save_weekly_review_from_sources(
        user_id=a,
        review=_review(),
        source_trade_ids=[t],
        input_fingerprint=FP1,
        job_id=1,
        verify=_ok,
    )
    created = _weekly_row(a)[0].created_at
    second = weekly.save_weekly_review_from_sources(
        user_id=a,
        review=_review("### What Worked\ny"),
        source_trade_ids=[t],
        input_fingerprint=FP2,
        job_id=2,
        verify=_ok,
    )
    assert first == second
    assert weekly.get_weekly_review("2026-09-07", a)["content_md"].endswith("y")
    rows = _weekly_row(a)
    assert len(rows) == 1
    assert rows[0].input_fingerprint == FP2
    assert rows[0].job_id == 2
    assert rows[0].created_at == created
    assert isinstance(rows[0].updated_at, dt.datetime)

    _delete_trade(t)
    with pytest.raises(daily_debriefs.ReviewSourceGone):
        weekly.save_weekly_review_from_sources(
            user_id=a,
            review=_review("### What Worked\nz"),
            source_trade_ids=[t],
            input_fingerprint=FP1,
            job_id=3,
            verify=_ok,
        )
    assert weekly.get_weekly_review("2026-09-07", a)["content_md"].endswith("y")


def test_weekly_save_with_a_failing_verifier_writes_nothing(two_users):
    a, _ = two_users
    t = _trade(a)
    with pytest.raises(daily_debriefs.ReviewSourceChanged):
        weekly.save_weekly_review_from_sources(
            user_id=a,
            review=_review(),
            source_trade_ids=[t],
            input_fingerprint=FP1,
            job_id=1,
            verify=lambda db: False,
        )
    assert _weekly_row(a) == []
