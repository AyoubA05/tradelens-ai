"""`/v1/reviews` — Patterns, review periods, and job-backed review generation.

Isolation tests authenticate the SECOND user as well as the first: a route that
hardcoded an owner would pass every test run as user one.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import secrets
import time

import pytest
from fastapi.testclient import TestClient

from src.tradelens.api.app import create_app
from src.tradelens.api.routers import reviews as reviews_router
from src.tradelens.api.security import sign_request
from src.tradelens.db.session import SessionLocal

SECRET = "test-service-secret-value-at-least-32-bytes"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("TL_SERVICE_SECRET", SECRET)
    monkeypatch.delenv("TL_SERVICE_SECRET_PREVIOUS", raising=False)
    monkeypatch.setenv("TL_ENV", "production")
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://user:password@example.invalid/tradelens?sslmode=require",
    )
    return TestClient(create_app(), raise_server_exceptions=False)


def _session_handle_for(user_id: int) -> str:
    from sqlalchemy import text as sa_text

    from src.tradelens.services import auth_sessions

    token = secrets.token_urlsafe(32)
    now = dt.datetime.now(dt.timezone.utc)
    digest = hashlib.sha256(
        (auth_sessions.WEBSITE_DOMAIN + token).encode("utf-8")
    ).hexdigest()
    db = SessionLocal()
    try:
        db.execute(
            sa_text(
                "INSERT INTO auth_sessions (token_hash, user_id, created_at, "
                "expires_at, last_seen_at, surface) VALUES (:h,:u,:c,:e,:l,:s)"
            ),
            {
                "h": digest,
                "u": user_id,
                "c": now,
                "e": now + dt.timedelta(hours=12),
                "l": now,
                "s": auth_sessions.SURFACE_WEBSITE,
            },
        )
        db.commit()
    finally:
        db.close()
    return digest


def _call(client, user_id, method, path, payload=None, *, sign=True, session=True):
    path_only, _, query = path.partition("?")
    body = b"" if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if sign:
        ts = str(int(time.time()))
        headers["X-TL-Signature"] = "v1={}:{}".format(
            ts, sign_request(SECRET, ts, method, path_only, query, body)
        )
    if session:
        headers["X-TL-Session-Handle"] = _session_handle_for(user_id)
    return client.request(method, path, content=body, headers=headers)


def _get(client, path, user_id):
    return _call(client, user_id, "GET", path)


def _post(client, path, body, user_id):
    return _call(client, user_id, "POST", path, body)


def _trade(owner, day, **extra):
    from src.tradelens.db.models import Trade

    fields = dict(
        user_id=owner,
        asset="NQ",
        direction="Long",
        result="Win",
        trade_date=day,
        pnl=50.0,
        setup_type="FVG",
        followed_rules=1,
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
    from src.tradelens.db.models import Trade

    db = SessionLocal()
    try:
        row = db.get(Trade, trade_id)
        for key, value in fields.items():
            setattr(row, key, value)
        db.commit()
    finally:
        db.close()


@pytest.fixture(autouse=True)
def _fixed_today(monkeypatch):
    """Every period in these tests is in the past relative to this instant."""
    monkeypatch.setattr(
        reviews_router,
        "_now_utc",
        lambda: dt.datetime(2026, 9, 14, 12, 0, tzinfo=dt.timezone.utc),
    )


ROUTES = [
    ("GET", "/v1/reviews", None),
    ("POST", "/v1/reviews/weekly", {"week": "2026-09-07"}),
    ("POST", "/v1/reviews/daily", {"day": "2026-09-08"}),
    ("GET", "/v1/reviews/jobs/1", None),
]


# ── both locks ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize("method, path, payload", ROUTES)
def test_every_review_route_needs_the_signature_and_a_live_session(
    client, two_users, method, path, payload
):
    b = two_users[1]
    assert _call(client, b, method, path, payload, sign=False).status_code == 401
    assert _call(client, b, method, path, payload, session=False).status_code == 401


# ── B1: GET /v1/reviews ────────────────────────────────────────────────────


def test_reviews_read_is_owner_scoped(client, two_users):
    a, b = two_users
    _trade(a, "2026-09-08")
    _trade(b, "2026-08-03")
    body = _get(client, "/v1/reviews", b).json()
    assert body["days"] == ["2026-08-03"]
    assert body["weeks"] == ["2026-08-03"]
    assert body["patterns"]["trades"] == 1
    assert body["complete_trades"] <= 1
    assert body["trades_for_review"] == 5


def test_patterns_are_deterministic_and_need_no_ai(client, two_users, monkeypatch):
    a, _ = two_users

    def _no_ai(*args, **kwargs):
        raise AssertionError("no AI")

    monkeypatch.setattr("src.tradelens.services.ai_client.chat", _no_ai)
    for i in range(4):
        _trade(a, "2026-09-0%d" % (i + 1), killzone="London Open")
    response = _get(client, "/v1/reviews", a)
    assert response.status_code == 200
    assert isinstance(response.json()["patterns"]["insights"], list)


def test_future_trade_days_are_not_offered(client, two_users):
    a, _ = two_users
    _trade(a, "2026-09-08")
    _trade(a, "2026-09-20")
    body = _get(client, "/v1/reviews", a).json()
    assert body["days"] == ["2026-09-08"]
    assert body["weeks"] == ["2026-09-07"]


@pytest.mark.parametrize(
    "zone, before, after, day",
    [
        (
            "America/New_York",
            dt.datetime(2026, 3, 9, 3, 59, tzinfo=dt.timezone.utc),
            dt.datetime(2026, 3, 9, 4, 0, tzinfo=dt.timezone.utc),
            "2026-03-09",
        ),
        (
            "Europe/London",
            dt.datetime(2026, 3, 29, 22, 59, tzinfo=dt.timezone.utc),
            dt.datetime(2026, 3, 29, 23, 0, tzinfo=dt.timezone.utc),
            "2026-03-30",
        ),
    ],
)
def test_not_future_follows_the_owner_zone_across_dst(
    client, two_users, monkeypatch, zone, before, after, day
):
    from src.tradelens.services import app_settings

    a, _ = two_users
    app_settings.set_timezone(a, zone)
    _trade(a, day)
    monkeypatch.setattr(reviews_router, "_now_utc", lambda: before)
    assert day not in _get(client, "/v1/reviews", a).json()["days"]
    monkeypatch.setattr(reviews_router, "_now_utc", lambda: after)
    assert day in _get(client, "/v1/reviews", a).json()["days"]


def test_saved_notes_are_returned_only_for_the_owner(client, two_users):
    from src.tradelens.services import daily_debriefs

    a, b = two_users
    t = _trade(a, "2026-09-08")
    daily_debriefs.save_daily_debrief(
        user_id=a,
        day="2026-09-08",
        input_fingerprint="k",
        job_id=None,
        result={
            "content_md": "### Session Summary\nok",
            "stats": {"trades": 1},
            "reviewed_trades": 1,
        },
        source_trade_ids=[t],
        verify=lambda db: True,
    )
    assert _get(client, "/v1/reviews?day=2026-09-08", a).json()["daily"]["content_md"]
    assert _get(client, "/v1/reviews?day=2026-09-08", b).json()["daily"] is None


@pytest.mark.parametrize(
    "query", ["?week=2026-9-7", "?day=tomorrow", "?owner=1", "?week=2026-09-08"]
)
def test_bad_or_unknown_query_is_422(client, two_users, query):
    a, _ = two_users
    assert _get(client, "/v1/reviews" + query, a).status_code == 422


# ── B2: weekly recap generation ────────────────────────────────────────────

WEEKLY = "/v1/reviews/weekly"


def _usage():
    from src.tradelens.services.ai_client import Usage

    return Usage("claude-opus-5", 1, 1, 0, 0.0, 0.0)


def _complete_week(owner, n=5):
    return [_trade(owner, "2026-09-%02d" % (7 + (i % 5))) for i in range(n)]


def _job(job_id):
    from src.tradelens.db.models import AIJob

    db = SessionLocal()
    try:
        return db.get(AIJob, job_id)
    finally:
        db.close()


def test_generate_weekly_enqueues_one_job_for_a_double_click(client, two_users):
    a, _ = two_users
    _complete_week(a)
    first = _post(client, WEEKLY, {"week": "2026-09-07"}, a)
    second = _post(client, WEEKLY, {"week": "2026-09-07"}, a)
    assert first.status_code == 202 and second.status_code == 202
    assert first.json()["job_id"] == second.json()["job_id"]
    assert (first.json()["created"], second.json()["created"]) == (True, False)


def test_weekly_job_payload_carries_ids_and_fingerprint_never_trade_text(
    client, two_users
):
    a, _ = two_users
    ids = _complete_week(a)
    _update_trade(ids[0], notes="PRIVATE_NOTE_TEXT")
    job = _job(_post(client, WEEKLY, {"week": "2026-09-07"}, a).json()["job_id"])
    payload = json.loads(job.payload)
    assert set(payload) == {"period", "source_trade_ids", "fingerprint", "key"}
    assert payload["period"] == "2026-09-07"
    assert payload["source_trade_ids"] == sorted(ids)
    assert payload["key"] == "weekly_recap:" + payload["fingerprint"]
    assert job.idempotency_key == payload["key"]
    assert "PRIVATE_NOTE_TEXT" not in job.payload


def test_a_changed_week_trade_is_a_new_job(client, two_users):
    a, _ = two_users
    ids = _complete_week(a)
    first = _post(client, WEEKLY, {"week": "2026-09-07"}, a).json()["job_id"]
    _update_trade(ids[0], pnl=-25.0, result="Loss")
    second = _post(client, WEEKLY, {"week": "2026-09-07"}, a).json()
    assert second["job_id"] != first and second["created"] is True


def test_an_added_week_trade_is_a_new_job(client, two_users):
    a, _ = two_users
    _complete_week(a)
    first = _post(client, WEEKLY, {"week": "2026-09-07"}, a).json()["job_id"]
    _trade(a, "2026-09-09")
    assert _post(client, WEEKLY, {"week": "2026-09-07"}, a).json()["job_id"] != first


def test_a_changed_strategy_profile_is_a_new_weekly_job(client, two_users):
    from src.tradelens.services import strategy

    a, _ = two_users
    _complete_week(a)
    first = _post(client, WEEKLY, {"week": "2026-09-07"}, a).json()["job_id"]
    strategy.upsert_strategy_profile(
        a, name="Plan", risk_rules="Two trades a day, then stop."
    )
    assert _post(client, WEEKLY, {"week": "2026-09-07"}, a).json()["job_id"] != first


def test_a_changed_weekly_prompt_is_a_new_job(client, two_users, monkeypatch):
    from src.tradelens.services import ai_client

    a, _ = two_users
    _complete_week(a)
    first = _post(client, WEEKLY, {"week": "2026-09-07"}, a).json()["job_id"]
    real = ai_client.load_prompt
    monkeypatch.setattr(ai_client, "load_prompt", lambda name: real(name) + "\nv2")
    assert _post(client, WEEKLY, {"week": "2026-09-07"}, a).json()["job_id"] != first


def test_a_changed_weekly_effort_is_a_new_key(client, two_users, monkeypatch):
    from src.tradelens.services import weekly

    a, _ = two_users
    _complete_week(a)
    first = _job(_post(client, WEEKLY, {"week": "2026-09-07"}, a).json()["job_id"])
    monkeypatch.setattr(weekly, "WEEKLY_EFFORT", "medium")
    second = _job(_post(client, WEEKLY, {"week": "2026-09-07"}, a).json()["job_id"])
    assert second.idempotency_key != first.idempotency_key


def test_weekly_refuses_empty_and_undersized(client, two_users):
    a, _ = two_users
    r = _post(client, WEEKLY, {"week": "2026-09-07"}, a)
    assert (r.status_code, r.json()["detail"]) == (409, "empty_period")
    _trade(a, "2026-09-08")
    r = _post(client, WEEKLY, {"week": "2026-09-07"}, a)
    assert (r.status_code, r.json()["detail"]) == (409, "not_enough_trades")


def test_weekly_refuses_a_future_week(client, two_users):
    a, _ = two_users
    _complete_week(a)
    for i in range(5):
        _trade(a, "2026-09-2%d" % (1 + i))
    r = _post(client, WEEKLY, {"week": "2026-09-21"}, a)
    assert (r.status_code, r.json()["detail"]) == (409, "empty_period")


def test_weekly_refuses_when_ai_context_is_unavailable(client, two_users, monkeypatch):
    from src.tradelens.services import trade_analysis

    a, _ = two_users
    _complete_week(a)

    def _raise(owner):
        raise trade_analysis.AIInputVersionUnavailable("down")

    monkeypatch.setattr(trade_analysis, "ai_input_version", _raise)
    r = _post(client, WEEKLY, {"week": "2026-09-07"}, a)
    assert (r.status_code, r.json()["detail"]) == (503, "review_unavailable")


@pytest.mark.parametrize(
    "body",
    [
        {"week": "2026-09-08"},
        {"week": "2026-09-07", "user_id": 1},
        {"week": "2026-09-07", "source_trade_ids": [1]},
        {"week": 20260907},
        {},
    ],
)
def test_weekly_body_is_strict(client, two_users, body):
    a, _ = two_users
    _complete_week(a)
    assert _post(client, WEEKLY, body, a).status_code == 422


def test_weekly_rate_limit_is_429_and_keeps_existing_jobs(
    client, two_users, monkeypatch
):
    from src.tradelens.services import weekly

    a, _ = two_users
    monkeypatch.setattr(weekly, "MAX_WEEKLY_PER_WINDOW", 1)
    _complete_week(a)
    first = _post(client, WEEKLY, {"week": "2026-09-07"}, a).json()["job_id"]
    _trade(a, "2026-09-10")
    limited = _post(client, WEEKLY, {"week": "2026-09-07"}, a)
    assert limited.status_code == 429
    assert limited.json()["detail"] == reviews_router.WEEKLY_LIMIT_MESSAGE
    assert _get(client, "/v1/reviews/jobs/%d" % first, a).status_code == 200


def test_job_poll_is_owner_scoped(client, two_users):
    a, b = two_users
    _complete_week(a)
    job = _post(client, WEEKLY, {"week": "2026-09-07"}, a).json()["job_id"]
    assert _get(client, "/v1/reviews/jobs/%d" % job, b).status_code == 404
    assert _get(client, "/v1/reviews/jobs/999999", a).status_code == 404
    queued = _get(client, "/v1/reviews/jobs/%d" % job, a).json()
    assert queued == {
        "job_id": job,
        "kind": "weekly_recap",
        "status": "queued",
        "note": None,
        "error": None,
    }


def test_job_poll_is_kind_scoped(client, two_users):
    from src.tradelens.api import jobs

    a, _ = two_users
    other, _ = jobs.enqueue(a, "trade_summary", "trade_summary:x", {})
    assert _get(client, "/v1/reviews/jobs/%d" % other, a).status_code == 404


def test_superseded_job_poll_shape(client, two_users):
    from src.tradelens.api import jobs

    a, _ = two_users
    _complete_week(a)
    job = _post(client, WEEKLY, {"week": "2026-09-07"}, a).json()["job_id"]
    jobs.complete(job, "weekly_recap:superseded")
    body = _get(client, "/v1/reviews/jobs/%d" % job, a).json()
    assert body["status"] == "superseded"
    assert body["note"] is None
    assert body["error"] == "This review is out of date. Generate it again."


@pytest.mark.parametrize(
    "ref",
    ["weekly_recap:", "weekly_recap:+1", "weekly_recap:1x", "daily_debrief:1", "x"],
)
def test_malformed_result_pointer_is_a_fixed_500(client, two_users, ref):
    from src.tradelens.api import jobs

    a, _ = two_users
    _complete_week(a)
    job = _post(client, WEEKLY, {"week": "2026-09-07"}, a).json()["job_id"]
    jobs.complete(job, ref)
    r = _get(client, "/v1/reviews/jobs/%d" % job, a)
    assert r.status_code == 500
    assert r.json()["detail"] == "review result unavailable"


def test_failed_job_poll_shows_only_the_stored_safe_message(client, two_users):
    from src.tradelens.api import jobs

    a, _ = two_users
    _complete_week(a)
    job = _post(client, WEEKLY, {"week": "2026-09-07"}, a).json()["job_id"]
    jobs.fail(job, "This could not be generated. Please try again.")
    body = _get(client, "/v1/reviews/jobs/%d" % job, a).json()
    assert (body["status"], body["note"]) == ("failed", None)
    assert body["error"] == "This could not be generated. Please try again."


def test_weekly_end_to_end_poll_returns_the_saved_note(client, two_users, monkeypatch):
    from src.tradelens.api import jobs, worker
    from src.tradelens.services import weekly

    a, b = two_users
    _complete_week(a)
    good = "\n\n".join("%s\nReflection." % h for h in weekly._REQUIRED_SECTIONS)
    monkeypatch.setattr(weekly, "chat", lambda **k: (good, _usage()))
    monkeypatch.setattr(worker, "log_ai_usage", lambda *x, **k: None)
    job = _post(client, WEEKLY, {"week": "2026-09-07"}, a).json()["job_id"]
    assert jobs.run_once(worker.HANDLERS) is True
    body = _get(client, "/v1/reviews/jobs/%d" % job, a).json()
    assert body["status"] == "succeeded" and body["error"] is None
    assert body["note"]["period"] == "2026-09-07"
    assert body["note"]["content_md"] == good
    assert body["note"]["reviewed_trades"] == 5
    assert _get(client, "/v1/reviews/jobs/%d" % job, b).status_code == 404
    saved = _get(client, "/v1/reviews?week=2026-09-07", a).json()["weekly"]
    assert saved["content_md"] == good


# ── B3: daily debrief generation ───────────────────────────────────────────

DAILY = "/v1/reviews/daily"


def test_generate_daily_enqueues_one_job_for_a_double_click(client, two_users):
    a, _ = two_users
    _trade(a, "2026-09-08")
    first = _post(client, DAILY, {"day": "2026-09-08"}, a)
    second = _post(client, DAILY, {"day": "2026-09-08"}, a)
    assert first.status_code == 202 and second.status_code == 202
    assert first.json()["job_id"] == second.json()["job_id"]
    assert (first.json()["created"], second.json()["created"]) == (True, False)


def test_daily_needs_no_weekly_gate(client, two_users):
    a, _ = two_users
    _trade(a, "2026-09-08")
    assert _post(client, DAILY, {"day": "2026-09-08"}, a).status_code == 202


def test_daily_job_payload_carries_ids_and_fingerprint_never_trade_text(
    client, two_users
):
    a, _ = two_users
    t = _trade(a, "2026-09-08", notes="PRIVATE_NOTE_TEXT")
    job = _job(_post(client, DAILY, {"day": "2026-09-08"}, a).json()["job_id"])
    payload = json.loads(job.payload)
    assert set(payload) == {"period", "source_trade_ids", "fingerprint", "key"}
    assert (payload["period"], payload["source_trade_ids"]) == ("2026-09-08", [t])
    assert payload["key"] == "daily_debrief:" + payload["fingerprint"]
    assert job.idempotency_key == payload["key"]
    assert "PRIVATE_NOTE_TEXT" not in job.payload


def test_a_changed_daily_note_is_a_new_job(client, two_users):
    a, _ = two_users
    t = _trade(a, "2026-09-08", notes="calm")
    first = _post(client, DAILY, {"day": "2026-09-08"}, a).json()["job_id"]
    _update_trade(t, notes="rushed the entry")
    second = _post(client, DAILY, {"day": "2026-09-08"}, a).json()
    assert second["job_id"] != first and second["created"] is True


def test_a_changed_daily_trade_is_a_new_job(client, two_users):
    a, _ = two_users
    t = _trade(a, "2026-09-08")
    first = _post(client, DAILY, {"day": "2026-09-08"}, a).json()["job_id"]
    _update_trade(t, pnl=-10.0, result="Loss")
    assert _post(client, DAILY, {"day": "2026-09-08"}, a).json()["job_id"] != first


def test_a_changed_strategy_profile_is_a_new_daily_job(client, two_users):
    from src.tradelens.services import strategy

    a, _ = two_users
    _trade(a, "2026-09-08")
    first = _post(client, DAILY, {"day": "2026-09-08"}, a).json()["job_id"]
    strategy.upsert_strategy_profile(a, name="Plan", risk_rules="One loss, stop.")
    assert _post(client, DAILY, {"day": "2026-09-08"}, a).json()["job_id"] != first


def test_a_changed_daily_prompt_is_a_new_job(client, two_users, monkeypatch):
    from src.tradelens.services import ai_client

    a, _ = two_users
    _trade(a, "2026-09-08")
    first = _post(client, DAILY, {"day": "2026-09-08"}, a).json()["job_id"]
    real = ai_client.load_prompt
    monkeypatch.setattr(ai_client, "load_prompt", lambda name: real(name) + "\nv2")
    assert _post(client, DAILY, {"day": "2026-09-08"}, a).json()["job_id"] != first


def test_a_changed_daily_effort_is_a_new_key(client, two_users, monkeypatch):
    from src.tradelens.services import debrief

    a, _ = two_users
    _trade(a, "2026-09-08")
    first = _job(_post(client, DAILY, {"day": "2026-09-08"}, a).json()["job_id"])
    monkeypatch.setattr(debrief, "DAILY_EFFORT", "high")
    second = _job(_post(client, DAILY, {"day": "2026-09-08"}, a).json()["job_id"])
    assert second.idempotency_key != first.idempotency_key


def test_daily_refuses_an_empty_day(client, two_users):
    a, b = two_users
    _trade(b, "2026-09-08")
    r = _post(client, DAILY, {"day": "2026-09-08"}, a)
    assert (r.status_code, r.json()["detail"]) == (409, "empty_period")


def test_daily_refuses_a_future_day(client, two_users):
    a, _ = two_users
    _trade(a, "2026-09-20")
    r = _post(client, DAILY, {"day": "2026-09-20"}, a)
    assert (r.status_code, r.json()["detail"]) == (409, "empty_period")


def test_daily_not_future_follows_the_owner_zone_across_dst(
    client, two_users, monkeypatch
):
    from src.tradelens.services import app_settings

    a, _ = two_users
    app_settings.set_timezone(a, "Europe/London")
    _trade(a, "2026-03-30")
    monkeypatch.setattr(
        reviews_router,
        "_now_utc",
        lambda: dt.datetime(2026, 3, 29, 22, 59, tzinfo=dt.timezone.utc),
    )
    r = _post(client, DAILY, {"day": "2026-03-30"}, a)
    assert (r.status_code, r.json()["detail"]) == (409, "empty_period")
    monkeypatch.setattr(
        reviews_router,
        "_now_utc",
        lambda: dt.datetime(2026, 3, 29, 23, 0, tzinfo=dt.timezone.utc),
    )
    assert _post(client, DAILY, {"day": "2026-03-30"}, a).status_code == 202


def test_daily_refuses_when_ai_context_is_unavailable(client, two_users, monkeypatch):
    from src.tradelens.services import trade_analysis

    a, _ = two_users
    _trade(a, "2026-09-08")

    def _raise(owner):
        raise trade_analysis.AIInputVersionUnavailable("down")

    monkeypatch.setattr(trade_analysis, "ai_input_version", _raise)
    r = _post(client, DAILY, {"day": "2026-09-08"}, a)
    assert (r.status_code, r.json()["detail"]) == (503, "review_unavailable")


@pytest.mark.parametrize(
    "body",
    [
        {"day": "2026-9-8"},
        {"day": "2026-09-08", "trades": [1]},
        {"day": "2026-09-08", "user_id": 1},
        {"day": 20260908},
        {},
    ],
)
def test_daily_body_is_strict(client, two_users, body):
    a, _ = two_users
    _trade(a, "2026-09-08")
    assert _post(client, DAILY, body, a).status_code == 422


def test_daily_rate_limit_is_429_and_keeps_existing_jobs(
    client, two_users, monkeypatch
):
    from src.tradelens.services import debrief

    a, _ = two_users
    monkeypatch.setattr(debrief, "MAX_DAILY_PER_WINDOW", 1)
    t = _trade(a, "2026-09-08")
    first = _post(client, DAILY, {"day": "2026-09-08"}, a).json()["job_id"]
    _update_trade(t, notes="changed")
    limited = _post(client, DAILY, {"day": "2026-09-08"}, a)
    assert limited.status_code == 429
    assert limited.json()["detail"] == reviews_router.DAILY_LIMIT_MESSAGE
    assert _get(client, "/v1/reviews/jobs/%d" % first, a).status_code == 200


def test_daily_job_poll_is_owner_scoped(client, two_users):
    a, b = two_users
    _trade(a, "2026-09-08")
    job = _post(client, DAILY, {"day": "2026-09-08"}, a).json()["job_id"]
    assert _get(client, "/v1/reviews/jobs/%d" % job, b).status_code == 404
    assert _get(client, "/v1/reviews/jobs/%d" % job, a).json()["kind"] == (
        "daily_debrief"
    )


def test_daily_superseded_job_poll_shape(client, two_users):
    from src.tradelens.api import jobs

    a, _ = two_users
    _trade(a, "2026-09-08")
    job = _post(client, DAILY, {"day": "2026-09-08"}, a).json()["job_id"]
    jobs.complete(job, "daily_debrief:superseded")
    body = _get(client, "/v1/reviews/jobs/%d" % job, a).json()
    assert (body["status"], body["note"]) == ("superseded", None)
    assert body["error"] == "This review is out of date. Generate it again."
    jobs.complete(job, "weekly_recap:1")
    assert _get(client, "/v1/reviews/jobs/%d" % job, a).status_code == 500


def test_daily_end_to_end_poll_returns_the_saved_note(client, two_users, monkeypatch):
    from src.tradelens.api import jobs, worker
    from src.tradelens.services import debrief

    a, b = two_users
    _trade(a, "2026-09-08")
    _trade(a, "2026-09-08", pnl=-20.0, result="Loss")
    good = "\n\n".join("%s\nReflection." % h for h in debrief._REQUIRED_SECTIONS)
    monkeypatch.setattr(debrief, "chat", lambda **k: (good, _usage()))
    monkeypatch.setattr(worker, "log_ai_usage", lambda *x, **k: None)
    job = _post(client, DAILY, {"day": "2026-09-08"}, a).json()["job_id"]
    assert jobs.run_once(worker.HANDLERS) is True
    body = _get(client, "/v1/reviews/jobs/%d" % job, a).json()
    assert body["status"] == "succeeded" and body["error"] is None
    assert body["note"]["period"] == "2026-09-08"
    assert body["note"]["content_md"] == good
    assert body["note"]["reviewed_trades"] == 2
    assert _get(client, "/v1/reviews/jobs/%d" % job, b).status_code == 404
    saved = _get(client, "/v1/reviews?day=2026-09-08", a).json()["daily"]
    assert saved["content_md"] == good


# ── C6: future-dated trades in the current week (one as-of-today rule) ────

_WEDNESDAY = dt.datetime(2026, 9, 16, 12, 0, tzinfo=dt.timezone.utc)
_SATURDAY = dt.datetime(2026, 9, 19, 12, 0, tzinfo=dt.timezone.utc)


def _pin_today(monkeypatch, instant):
    from src.tradelens.services import review_inputs

    monkeypatch.setattr(reviews_router, "_now_utc", lambda: instant)
    monkeypatch.setattr(review_inputs, "_now_utc", lambda: instant)


def test_a_friday_trade_is_not_in_a_wednesday_weekly_job(
    client, two_users, monkeypatch
):
    a, _ = two_users
    _complete_week(a)
    wed = _trade(a, "2026-09-16")
    fri = _trade(a, "2026-09-18")
    _pin_today(monkeypatch, _WEDNESDAY)
    job = _post(client, WEEKLY, {"week": "2026-09-14"}, a).json()["job_id"]
    ids = json.loads(_job(job).payload)["source_trade_ids"]
    assert ids == [wed] and fri not in ids


def test_router_and_worker_fingerprints_match_on_the_same_owner_day(
    client, two_users, monkeypatch
):
    from src.tradelens.api import jobs, worker
    from src.tradelens.services import weekly

    a, _ = two_users
    _complete_week(a)
    _trade(a, "2026-09-16")
    _trade(a, "2026-09-18")
    _pin_today(monkeypatch, _WEDNESDAY)
    good = "\n\n".join("%s\nReflection." % h for h in weekly._REQUIRED_SECTIONS)
    monkeypatch.setattr(weekly, "chat", lambda **k: (good, _usage()))
    monkeypatch.setattr(worker, "log_ai_usage", lambda *x, **k: None)
    job = _post(client, WEEKLY, {"week": "2026-09-14"}, a).json()["job_id"]
    assert jobs.run_once(worker.HANDLERS) is True
    body = _get(client, "/v1/reviews/jobs/%d" % job, a).json()
    assert body["status"] == "succeeded"
    assert body["note"]["reviewed_trades"] == 1


def test_a_job_whose_week_gains_an_eligible_trade_when_today_advances_is_superseded(
    client, two_users, monkeypatch
):
    """Documented behaviour: the Friday trade becomes eligible on Saturday, so
    the Wednesday job no longer describes the week and saves nothing."""
    from src.tradelens.api import jobs, worker
    from src.tradelens.services import weekly

    a, _ = two_users
    _complete_week(a)
    _trade(a, "2026-09-16")
    _trade(a, "2026-09-18")
    _pin_today(monkeypatch, _WEDNESDAY)
    job = _post(client, WEEKLY, {"week": "2026-09-14"}, a).json()["job_id"]

    def _never(**k):
        raise AssertionError("provider must not be called")

    monkeypatch.setattr(weekly, "chat", _never)
    _pin_today(monkeypatch, _SATURDAY)
    assert jobs.run_once(worker.HANDLERS) is True
    assert _get(client, "/v1/reviews/jobs/%d" % job, a).json()["status"] == (
        "superseded"
    )


# ── result pointer: owner filter and strict parsing (fix items 4, 5) ──────


def _weekly_row(owner, week="2026-09-07"):
    from src.tradelens.services import weekly

    good = "\n\n".join("%s\nReflection." % h for h in weekly._REQUIRED_SECTIONS)
    saved = weekly.save_weekly_review(
        {"week_start": week, "content_md": good, "stats": {"trades": 5}},
        owner,
        overwrite=True,
    )
    return int(saved["id"])


def _daily_row(owner, day="2026-09-08"):
    from src.tradelens.services import daily_debriefs

    tid = _trade(owner, day)
    return daily_debriefs.save_daily_debrief(
        user_id=owner,
        day=day,
        input_fingerprint="x" * 64,
        job_id=None,
        result={"content_md": "### Session Summary\nB only.", "reviewed_trades": 1},
        source_trade_ids=[tid],
        verify=lambda db: True,
    )


def test_weekly_poll_never_reads_another_owners_row(client, two_users):
    from src.tradelens.api import jobs

    a, b = two_users
    _complete_week(a)
    foreign = _weekly_row(b)
    job = _post(client, WEEKLY, {"week": "2026-09-07"}, a).json()["job_id"]
    jobs.complete(job, "weekly_recap:%d" % foreign)
    r = _get(client, "/v1/reviews/jobs/%d" % job, a)
    assert r.status_code == 500
    assert r.json() == {"detail": "review result unavailable"}


def test_daily_poll_never_reads_another_owners_row(client, two_users):
    from src.tradelens.api import jobs

    a, b = two_users
    _trade(a, "2026-09-08")
    foreign = _daily_row(b)
    job = _post(client, DAILY, {"day": "2026-09-08"}, a).json()["job_id"]
    jobs.complete(job, "daily_debrief:%d" % foreign)
    r = _get(client, "/v1/reviews/jobs/%d" % job, a)
    assert r.status_code == 500
    assert "B only" not in r.text


@pytest.mark.parametrize("shape", ["+%d", " %d", "%d.0", "%d "])
def test_result_pointer_must_be_bare_digits_for_a_real_row(client, two_users, shape):
    from src.tradelens.api import jobs

    a, _ = two_users
    _complete_week(a)
    own = _weekly_row(a)
    job = _post(client, WEEKLY, {"week": "2026-09-07"}, a).json()["job_id"]
    jobs.complete(job, "weekly_recap:" + shape % own)
    r = _get(client, "/v1/reviews/jobs/%d" % job, a)
    assert r.status_code == 500
    assert r.json() == {"detail": "review result unavailable"}
