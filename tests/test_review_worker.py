"""Review job handlers: fingerprint re-checks, usage logging, no resurrection."""

from __future__ import annotations

import pytest

from src.tradelens.api import jobs, worker
from src.tradelens.db.models import DailyDebrief, Trade, WeeklyReview
from src.tradelens.db.session import SessionLocal
from src.tradelens.services import daily_debriefs, debrief, review_inputs, weekly

MONDAY = "2026-09-07"
DAY = "2026-09-08"
GOOD_WEEKLY = "\n\n".join("%s\nReflection." % h for h in weekly._REQUIRED_SECTIONS)
GOOD_DAILY = "\n\n".join("%s\nReflection." % h for h in debrief._REQUIRED_SECTIONS)


def _usage():
    from src.tradelens.services.ai_client import Usage

    return Usage("claude-opus-5", 1, 1, 0, 0.0, 0.0)


def _trade(owner, day, **extra):
    fields = dict(
        user_id=owner,
        asset="NQ",
        direction="Long",
        result="Win",
        trade_date=day,
        pnl=5.0,
    )
    fields.update(extra)
    db = SessionLocal()
    try:
        row = Trade(**fields)
        db.add(row)
        db.commit()
        return row.id
    finally:
        db.close()


def _update_trade(trade_id, **fields):
    db = SessionLocal()
    try:
        row = db.get(Trade, trade_id)
        for key, value in fields.items():
            setattr(row, key, value)
        db.commit()
    finally:
        db.close()


def _delete_trades(owner):
    db = SessionLocal()
    try:
        db.query(Trade).filter(Trade.user_id == owner).delete()
        db.commit()
    finally:
        db.close()


def _queue_weekly(owner, monday=MONDAY):
    """Queue a weekly job exactly as the router does; returns (job_id, payload)."""
    model_input = weekly.build_weekly_model_input(owner, monday)
    fp = review_inputs.review_input_fingerprint(
        weekly.WEEKLY_JOB_KIND, owner, monday, model_input
    )
    key = weekly.WEEKLY_JOB_KIND + ":" + fp
    payload = {
        "period": monday,
        "source_trade_ids": model_input["source_trade_ids"],
        "fingerprint": fp,
        "key": key,
    }
    job_id, _ = jobs.enqueue(owner, weekly.WEEKLY_JOB_KIND, key, payload)
    return job_id, payload


def _weekly_rows(owner):
    db = SessionLocal()
    try:
        return db.query(WeeklyReview).filter(WeeklyReview.user_id == owner).count()
    finally:
        db.close()


@pytest.fixture
def quiet_usage(monkeypatch):
    logged = []
    monkeypatch.setattr(
        worker,
        "log_ai_usage",
        lambda feature, usage, user_id: logged.append((feature, user_id)),
    )
    return logged


# ── weekly ─────────────────────────────────────────────────────────────────


def test_weekly_handler_is_registered():
    assert worker.HANDLERS["weekly_recap"] is worker._weekly_recap_handler


def test_weekly_handler_saves_with_provenance(two_users, monkeypatch, quiet_usage):
    a, _ = two_users
    _trade(a, "2026-09-08")
    job_id, payload = _queue_weekly(a)
    monkeypatch.setattr(weekly, "chat", lambda **k: (GOOD_WEEKLY, _usage()))
    ref = worker._weekly_recap_handler(a, payload)
    kind, _, row_id = ref.partition(":")
    assert kind == "weekly_recap"
    saved = weekly.get_weekly_review_by_id(int(row_id), a)
    assert saved["content_md"] == GOOD_WEEKLY
    db = SessionLocal()
    try:
        row = db.get(WeeklyReview, int(row_id))
        assert (row.input_fingerprint, row.job_id) == (payload["fingerprint"], job_id)
    finally:
        db.close()


def test_weekly_handler_sends_the_same_corrections_block_it_fingerprints(
    two_users, monkeypatch, quiet_usage
):
    a, _ = two_users
    _trade(a, "2026-09-08")
    marker = "<past_corrections>exact captured block</past_corrections>"
    model_input = weekly.build_weekly_model_input(a, MONDAY)
    fingerprint = review_inputs.review_input_fingerprint(
        weekly.WEEKLY_JOB_KIND,
        a,
        MONDAY,
        model_input,
        corrections_block=marker,
    )
    key = weekly.WEEKLY_JOB_KIND + ":" + fingerprint
    payload = {
        "period": MONDAY,
        "source_trade_ids": model_input["source_trade_ids"],
        "fingerprint": fingerprint,
        "key": key,
    }
    jobs.enqueue(a, weekly.WEEKLY_JOB_KIND, key, payload)
    monkeypatch.setattr(worker, "review_corrections_block", lambda owner: marker)

    def fake_chat(**kwargs):
        assert kwargs["corrections_block"] == marker
        return GOOD_WEEKLY, _usage()

    monkeypatch.setattr(weekly, "chat", fake_chat)
    assert worker._weekly_recap_handler(a, payload).startswith("weekly_recap:")
    assert quiet_usage == [("Weekly Review", a)]


def test_weekly_handler_logs_usage_even_when_validation_fails(
    two_users, monkeypatch, quiet_usage
):
    a, _ = two_users
    _trade(a, "2026-09-08")
    _, payload = _queue_weekly(a)
    monkeypatch.setattr(
        weekly, "chat", lambda **k: ("### What Worked\nonly one", _usage())
    )
    with pytest.raises(weekly.WeeklyReviewError):
        worker._weekly_recap_handler(a, payload)
    assert quiet_usage == [("Weekly Review", a)]
    assert _weekly_rows(a) == 0


def test_weekly_handler_refuses_trade_guidance(two_users, monkeypatch, quiet_usage):
    a, _ = two_users
    _trade(a, "2026-09-08")
    job_id, payload = _queue_weekly(a)
    bad = GOOD_WEEKLY.replace("Reflection.", "Next week, short the open.", 1)
    monkeypatch.setattr(weekly, "chat", lambda **k: (bad, _usage()))
    with pytest.raises(weekly.WeeklyReviewError):
        worker._weekly_recap_handler(a, payload)
    assert _weekly_rows(a) == 0
    # Through the runner, a guard rejection fails the job.
    assert jobs.run_once(worker.HANDLERS) is True
    assert jobs.get_owned_job(job_id, a).status == "failed"


def test_weekly_pre_provider_mismatch_spends_nothing(
    two_users, monkeypatch, quiet_usage
):
    a, _ = two_users
    tid = _trade(a, "2026-09-08")
    _, payload = _queue_weekly(a)
    _update_trade(tid, pnl=-40.0, result="Loss")

    def _never(**kwargs):
        raise AssertionError("provider must not be called")

    monkeypatch.setattr(weekly, "chat", _never)
    assert worker._weekly_recap_handler(a, payload) == "weekly_recap:superseded"
    assert quiet_usage == []
    assert _weekly_rows(a) == 0


def test_weekly_pre_save_mismatch_writes_nothing(two_users, monkeypatch, quiet_usage):
    a, _ = two_users
    tid = _trade(a, "2026-09-08")
    _, payload = _queue_weekly(a)

    def _chat_then_edit(**kwargs):
        _update_trade(tid, pnl=-40.0, result="Loss")
        return GOOD_WEEKLY, _usage()

    monkeypatch.setattr(weekly, "chat", _chat_then_edit)
    assert worker._weekly_recap_handler(a, payload) == "weekly_recap:superseded"
    assert quiet_usage == [("Weekly Review", a)]
    assert _weekly_rows(a) == 0


def test_weekly_sources_deleted_mid_run_are_not_resurrected(
    two_users, monkeypatch, quiet_usage
):
    a, _ = two_users
    _trade(a, "2026-09-08")
    _, payload = _queue_weekly(a)

    def _chat_then_delete(**kwargs):
        _delete_trades(a)
        return GOOD_WEEKLY, _usage()

    monkeypatch.setattr(weekly, "chat", _chat_then_delete)
    assert worker._weekly_recap_handler(a, payload) == "weekly_recap:superseded"
    assert weekly.get_weekly_review(MONDAY, a) is None


def test_weekly_sources_deleted_before_run_spend_nothing(
    two_users, monkeypatch, quiet_usage
):
    a, _ = two_users
    _trade(a, "2026-09-08")
    _, payload = _queue_weekly(a)
    _delete_trades(a)

    def _never(**kwargs):
        raise AssertionError("provider must not be called")

    monkeypatch.setattr(weekly, "chat", _never)
    assert worker._weekly_recap_handler(a, payload) == "weekly_recap:superseded"
    assert weekly.get_weekly_review(MONDAY, a) is None


# ── daily ──────────────────────────────────────────────────────────────────


def _queue_daily(owner, day=DAY):
    """Queue a daily job exactly as the router does; returns (job_id, payload)."""
    model_input = debrief.build_daily_model_input(owner, day)
    fp = review_inputs.review_input_fingerprint(
        debrief.DAILY_JOB_KIND, owner, day, model_input
    )
    key = debrief.DAILY_JOB_KIND + ":" + fp
    payload = {
        "period": day,
        "source_trade_ids": model_input["source_trade_ids"],
        "fingerprint": fp,
        "key": key,
    }
    job_id, _ = jobs.enqueue(owner, debrief.DAILY_JOB_KIND, key, payload)
    return job_id, payload


def _daily_rows(owner):
    db = SessionLocal()
    try:
        return db.query(DailyDebrief).filter(DailyDebrief.user_id == owner).count()
    finally:
        db.close()


def test_daily_handler_is_registered():
    assert worker.HANDLERS["daily_debrief"] is worker._daily_debrief_handler


def test_daily_model_input_includes_ids_and_truncated_notes(two_users):
    a, _ = two_users
    t = _trade(a, DAY, notes="x" * 500)
    model_input = debrief.build_daily_model_input(a, DAY)
    assert model_input["source_trade_ids"] == [t]
    assert model_input["period_label"] == "Trading day " + DAY
    assert model_input["trades"][0]["notes"] == "x" * 200


def test_daily_handler_saves_with_provenance(two_users, monkeypatch, quiet_usage):
    a, _ = two_users
    _trade(a, DAY)
    _trade(a, DAY, pnl=-3.0, result="Loss")
    job_id, payload = _queue_daily(a)
    seen = {}

    def _chat(**kwargs):
        seen.update(kwargs)
        return GOOD_DAILY, _usage()

    monkeypatch.setattr(debrief, "chat", _chat)
    ref = worker._daily_debrief_handler(a, payload)
    kind, _, row_id = ref.partition(":")
    assert kind == "daily_debrief"
    saved = daily_debriefs.get_daily_debrief_by_id(int(row_id), a)
    assert saved["content_md"] == GOOD_DAILY
    assert saved["reviewed_trades"] == 2
    assert (saved["input_fingerprint"], saved["job_id"]) == (
        payload["fingerprint"],
        job_id,
    )
    assert "Period: Trading day " + DAY in seen["user_message"]
    assert quiet_usage == [("Daily Debrief", a)]


def test_daily_handler_logs_usage_even_when_validation_fails(
    two_users, monkeypatch, quiet_usage
):
    a, _ = two_users
    _trade(a, DAY)
    _, payload = _queue_daily(a)
    monkeypatch.setattr(
        debrief, "chat", lambda **k: ("### Session Summary\nonly one", _usage())
    )
    with pytest.raises(debrief.DebriefError):
        worker._daily_debrief_handler(a, payload)
    assert quiet_usage == [("Daily Debrief", a)]
    assert _daily_rows(a) == 0


def test_daily_handler_refuses_trade_guidance(two_users, monkeypatch, quiet_usage):
    a, _ = two_users
    _trade(a, DAY)
    job_id, payload = _queue_daily(a)
    bad = GOOD_DAILY.replace("Reflection.", "Tomorrow, buy above 20150.", 1)
    monkeypatch.setattr(debrief, "chat", lambda **k: (bad, _usage()))
    with pytest.raises(debrief.DebriefError):
        worker._daily_debrief_handler(a, payload)
    assert _daily_rows(a) == 0
    assert jobs.run_once(worker.HANDLERS) is True
    assert jobs.get_owned_job(job_id, a).status == "failed"


def test_daily_pre_provider_mismatch_spends_nothing(
    two_users, monkeypatch, quiet_usage
):
    a, _ = two_users
    t = _trade(a, DAY, notes="calm")
    _, payload = _queue_daily(a)
    _update_trade(t, notes="edited after queueing")

    def _never(**kwargs):
        raise AssertionError("provider must not be called")

    monkeypatch.setattr(debrief, "chat", _never)
    assert worker._daily_debrief_handler(a, payload) == "daily_debrief:superseded"
    assert quiet_usage == []
    assert _daily_rows(a) == 0


def test_daily_pre_save_mismatch_writes_nothing(two_users, monkeypatch, quiet_usage):
    a, _ = two_users
    t = _trade(a, DAY, notes="calm")
    _, payload = _queue_daily(a)

    def _chat_then_edit(**kwargs):
        _update_trade(t, notes="edited during the provider call")
        return GOOD_DAILY, _usage()

    monkeypatch.setattr(debrief, "chat", _chat_then_edit)
    assert worker._daily_debrief_handler(a, payload) == "daily_debrief:superseded"
    assert quiet_usage == [("Daily Debrief", a)]
    assert _daily_rows(a) == 0


def test_daily_sources_deleted_mid_run_are_not_resurrected(
    two_users, monkeypatch, quiet_usage
):
    a, _ = two_users
    _trade(a, DAY)
    _, payload = _queue_daily(a)

    def _chat_then_delete(**kwargs):
        _delete_trades(a)
        return GOOD_DAILY, _usage()

    monkeypatch.setattr(debrief, "chat", _chat_then_delete)
    assert worker._daily_debrief_handler(a, payload) == "daily_debrief:superseded"
    assert daily_debriefs.get_daily_debrief(user_id=a, day=DAY) is None


def test_daily_sources_deleted_before_run_spend_nothing(
    two_users, monkeypatch, quiet_usage
):
    a, _ = two_users
    _trade(a, DAY)
    _, payload = _queue_daily(a)
    _delete_trades(a)

    def _never(**kwargs):
        raise AssertionError("provider must not be called")

    monkeypatch.setattr(debrief, "chat", _never)
    assert worker._daily_debrief_handler(a, payload) == "daily_debrief:superseded"
    assert daily_debriefs.get_daily_debrief(user_id=a, day=DAY) is None


# ── locked verify reads through the save's own Session (fix item 3) ───────


def _spy_sessions(monkeypatch):
    seen = {"save": [], "locked": []}
    real_lock = daily_debriefs.lock_and_verify_sources
    real_locked = worker.locked_period_trades

    def lock_spy(db, owner, ids, verify):
        seen["save"].append(db)
        return real_lock(db, owner, ids, verify)

    def locked_spy(db, owner, start, end):
        seen["locked"].append(db)
        return real_locked(db, owner, start, end)

    monkeypatch.setattr(daily_debriefs, "lock_and_verify_sources", lock_spy)
    monkeypatch.setattr(worker, "locked_period_trades", locked_spy)
    return seen


def test_weekly_verify_reads_through_the_locking_session(
    two_users, monkeypatch, quiet_usage
):
    a, _ = two_users
    _trade(a, "2026-09-08")
    _, payload = _queue_weekly(a)
    monkeypatch.setattr(weekly, "chat", lambda **k: (GOOD_WEEKLY, _usage()))
    seen = _spy_sessions(monkeypatch)
    ref = worker._weekly_recap_handler(a, payload)
    assert ref.split(":")[1].isdigit()
    assert len(seen["save"]) == 1 and len(seen["locked"]) == 1
    assert seen["locked"][0] is seen["save"][0]


def test_daily_verify_reads_through_the_locking_session(
    two_users, monkeypatch, quiet_usage
):
    a, _ = two_users
    _trade(a, DAY)
    _, payload = _queue_daily(a)
    monkeypatch.setattr(debrief, "chat", lambda **k: (GOOD_DAILY, _usage()))
    seen = _spy_sessions(monkeypatch)
    ref = worker._daily_debrief_handler(a, payload)
    assert ref.split(":")[1].isdigit()
    assert len(seen["save"]) == 1 and len(seen["locked"]) == 1
    assert seen["locked"][0] is seen["save"][0]
