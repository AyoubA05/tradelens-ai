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
