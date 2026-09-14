"""`/v1/settings` — the Settings API.

Isolation tests authenticate the SECOND user: a route that hardcodes
`user_id=1` would pass every test run as the first. Destructive routes are
tested for the three things that matter: the exact typed confirmation, the
owner from the session, and that a blocked cleanup is a 503 with nothing
deleted — never a success.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import secrets
import time

import pytest
from fastapi.testclient import TestClient

from src.tradelens.api import storage
from src.tradelens.api.app import create_app
from src.tradelens.api.routers import settings as settings_router
from src.tradelens.api.schemas.settings import SettingsResponse
from src.tradelens.api.security import sign_request
from src.tradelens.api.storage import ObjectCleanup
from src.tradelens.db.session import SessionLocal
from src.tradelens.services import app_settings, csvio, sample_data
from src.tradelens.services.data_deletion import DeletionOutcome

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


def _call(client, handle, method, path, payload=None, *, sign=True):
    body = b"" if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if sign:
        ts = str(int(time.time()))
        headers["X-TL-Signature"] = "v1={}:{}".format(
            ts, sign_request(SECRET, ts, method, path, "", body)
        )
    if handle is not None:
        headers["X-TL-Session-Handle"] = handle
    return client.request(method, path, content=body, headers=headers)


ROUTES = [
    ("GET", "/v1/settings", None),
    ("PUT", "/v1/settings/timezone", {"timezone": "UTC"}),
    ("POST", "/v1/settings/sample-trades", {}),
    ("DELETE", "/v1/settings/sample-trades", None),
    ("GET", "/v1/settings/export", None),
    ("POST", "/v1/settings/import", {"csv": "a\n"}),
    ("POST", "/v1/settings/delete-trades", {"confirm": "DELETE"}),
    ("POST", "/v1/settings/delete-account", {"confirm": "DELETE MY ACCOUNT"}),
]


# ── both locks ─────────────────────────────────────────────────────────────


@pytest.mark.parametrize("method, path, payload", ROUTES)
def test_every_route_needs_the_signature_and_a_live_session(
    client, two_users, monkeypatch, method, path, payload
):
    touched = []
    monkeypatch.setattr(
        settings_router,
        "delete_all_trades_and_objects",
        lambda u: touched.append(u),
    )
    monkeypatch.setattr(
        settings_router, "delete_account_and_objects", lambda u: touched.append(u)
    )
    handle = _session_handle_for(two_users[1])
    assert _call(client, handle, method, path, payload, sign=False).status_code == 401
    assert _call(client, None, method, path, payload).status_code == 401
    assert _call(client, "0" * 64, method, path, payload).status_code == 401
    assert touched == []


# ── read ───────────────────────────────────────────────────────────────────


def test_settings_read_is_the_session_owners_not_user_one(client, two_users):
    first, second = two_users
    app_settings.set_timezone(first, "Asia/Tokyo")
    app_settings.set_timezone(second, "Europe/London")
    sample_data.load_sample_trades(first)
    body = _call(client, _session_handle_for(second), "GET", "/v1/settings").json()
    SettingsResponse.model_validate(body)
    assert body["timezone"] == {
        "current": "Europe/London",
        "options": list(app_settings.TIMEZONE_OPTIONS),
    }
    assert body["data"]["trade_count"] == 0
    assert body["data"]["sample_count"] == 0
    assert body["data"]["max_import_rows"] == csvio.MAX_IMPORT_ROWS


@pytest.mark.parametrize(
    "key, demo, expected",
    [
        (True, False, "enabled"),
        (True, True, "enabled"),
        (False, True, "demo"),
        (False, False, "unavailable"),
    ],
)
def test_ai_state_is_one_of_three_fixed_values(
    client, two_users, monkeypatch, key, demo, expected
):
    monkeypatch.setattr(settings_router, "has_api_key", lambda: key)
    monkeypatch.setattr(settings_router, "is_demo", lambda: demo)
    body = _call(
        client, _session_handle_for(two_users[1]), "GET", "/v1/settings"
    ).json()
    assert body["ai"] == {"state": expected}
    assert body["demo_mode"] is demo
    assert "ANTHROPIC" not in json.dumps(body)


def test_cost_is_this_owners_current_month(client, two_users, monkeypatch):
    import pandas as pd

    owner = two_users[1]
    seen = []

    def fake(year, month, user_id):
        seen.append((year, month, user_id))
        return pd.DataFrame(
            [
                {"feature": "AI Partner", "cost_usd": 0.0123, "calls": 2},
                {"feature": "Weekly Review", "cost_usd": 0.0100, "calls": 1},
            ]
        )

    monkeypatch.setattr(settings_router, "monthly_cost_by_feature", fake)
    body = _call(client, _session_handle_for(owner), "GET", "/v1/settings").json()
    today = app_settings.today_for_owner(owner)
    assert seen == [(today.year, today.month, owner)]
    assert body["cost"]["month"] == "{:04d}-{:02d}".format(today.year, today.month)
    assert body["cost"]["rows"][0] == {
        "feature": "AI Partner",
        "cost_usd": 0.0123,
        "calls": 2,
    }
    assert body["cost"]["total_usd"] == 0.0223


def test_the_email_is_reported_and_there_is_no_email_write_route(client, two_users):
    owner = two_users[1]
    body = _call(client, _session_handle_for(owner), "GET", "/v1/settings").json()
    assert set(body["account"]) == {"username", "email", "email_verified"}
    # Decision S1: display-only. No route may change the sign-in email.
    for method in ("PUT", "POST", "PATCH"):
        r = _call(
            client,
            _session_handle_for(owner),
            method,
            "/v1/settings/email",
            {"email": "x@example.com"},
        )
        assert r.status_code in (404, 405)


# ── timezone ───────────────────────────────────────────────────────────────


def test_a_listed_timezone_is_saved_and_returned(client, two_users):
    owner = two_users[1]
    r = _call(
        client,
        _session_handle_for(owner),
        "PUT",
        "/v1/settings/timezone",
        {"timezone": "Asia/Dubai"},
    )
    assert r.status_code == 200
    assert r.json()["timezone"]["current"] == "Asia/Dubai"
    assert app_settings.get_timezone(owner) == "Asia/Dubai"


@pytest.mark.parametrize(
    "bad", ["Mars/Olympus", "america/new_york", " UTC", "Not/AZone"]
)
def test_an_unlisted_timezone_is_422_by_field_and_code_and_stores_nothing(
    client, two_users, bad
):
    owner = two_users[1]
    app_settings.set_timezone(owner, "UTC")
    r = _call(
        client,
        _session_handle_for(owner),
        "PUT",
        "/v1/settings/timezone",
        {"timezone": bad},
    )
    assert r.status_code == 422
    assert r.json() == {"detail": [{"field": "timezone", "problem": "unsupported"}]}
    assert bad.strip() not in r.text or bad.strip() == "UTC"
    assert app_settings.get_timezone(owner) == "UTC"


@pytest.mark.parametrize(
    "payload",
    [
        {"timezone": "UTC", "user_id": 1},
        {"timezone": "UTC", "owner": 1},
        {"tz": "UTC"},
        {"timezone": 5},
        {"timezone": "x" * 65},
        {},
    ],
)
def test_the_timezone_write_is_a_strict_allowlist(client, two_users, payload):
    owner = two_users[1]
    app_settings.set_timezone(owner, "UTC")
    r = _call(
        client, _session_handle_for(owner), "PUT", "/v1/settings/timezone", payload
    )
    assert r.status_code == 422
    assert app_settings.get_timezone(owner) == "UTC"


# ── sample trades ──────────────────────────────────────────────────────────


def test_sample_trades_load_and_clear_only_this_owners(client, two_users):
    first, second = two_users
    sample_data.load_sample_trades(first)
    handle = _session_handle_for(second)
    loaded = _call(client, handle, "POST", "/v1/settings/sample-trades", {}).json()
    assert loaded == {
        "count": sample_data.SAMPLE_COUNT,
        "sample_count": sample_data.SAMPLE_COUNT,
    }
    cleared = _call(client, handle, "DELETE", "/v1/settings/sample-trades").json()
    assert cleared == {"count": sample_data.SAMPLE_COUNT, "sample_count": 0}
    assert sample_data.count_sample_trades(first) == sample_data.SAMPLE_COUNT


@pytest.mark.parametrize("method", ["POST", "DELETE"])
def test_sample_replacement_never_reports_success_over_failed_object_cleanup(
    client, two_users, monkeypatch, method
):
    owner = two_users[1]
    sample_data.load_sample_trades(owner)
    db = SessionLocal()
    try:
        from src.tradelens.db.models import Screenshot, Trade

        trade_id = (
            db.query(Trade.id)
            .filter(Trade.user_id == owner, Trade.is_sample == 1)
            .order_by(Trade.id)
            .first()[0]
        )
        key = "u/{}/t/{}/00000000-0000-4000-8000-000000000001.png".format(
            owner, trade_id
        )
        db.add(Screenshot(trade_id=trade_id, file_path=key))
        db.commit()
    finally:
        db.close()

    monkeypatch.setattr(
        storage,
        "delete_trade_objects",
        lambda user_id, candidate: ObjectCleanup(
            deleted=[], failed=[key] if candidate == trade_id else [], skipped=[]
        ),
    )
    response = _call(
        client,
        _session_handle_for(owner),
        method,
        "/v1/settings/sample-trades",
        {} if method == "POST" else None,
    )
    assert response.status_code == 503
    assert response.json() == {
        "detail": {
            "error": "screenshot_cleanup_failed",
            "remaining": 1,
            "unresolvable": 0,
        }
    }

    db = SessionLocal()
    try:
        from src.tradelens.db.models import Screenshot, Trade

        assert db.query(Trade).filter(Trade.id == trade_id).count() == 1
        assert db.query(Screenshot).filter(Screenshot.trade_id == trade_id).count() == 1
    finally:
        db.close()


# ── CSV ────────────────────────────────────────────────────────────────────


def test_export_contains_only_this_owners_trades(client, two_users):
    first, second = two_users
    sample_data.load_sample_trades(first)
    handle = _session_handle_for(second)
    body = _call(client, handle, "GET", "/v1/settings/export").json()
    assert body["filename"] == "trades.csv"
    assert body["row_count"] == 0
    assert body["csv"].splitlines()[0].split(",") == csvio.CSV_COLUMNS

    sample_data.load_sample_trades(second)
    body = _call(client, handle, "GET", "/v1/settings/export").json()
    assert body["row_count"] == sample_data.SAMPLE_COUNT
    assert len(body["csv"].strip().splitlines()) == sample_data.SAMPLE_COUNT + 1


def test_import_inserts_for_the_session_owner_and_reports_counts(client, two_users):
    first, owner = two_users
    text = "trade_date,asset,direction,result,pnl\n2026-09-01,NQ,Long,Win,100\n"
    handle = _session_handle_for(owner)
    r = _call(client, handle, "POST", "/v1/settings/import", {"csv": text})
    assert r.status_code == 200
    assert r.json() == {"inserted": 1, "skipped": 0, "errors": []}
    again = _call(client, handle, "POST", "/v1/settings/import", {"csv": text})
    assert again.json() == {"inserted": 0, "skipped": 1, "errors": []}
    assert (
        _call(client, _session_handle_for(first), "GET", "/v1/settings").json()["data"][
            "trade_count"
        ]
        == 0
    )


def test_an_import_over_the_row_cap_is_422_and_inserts_nothing(
    client, two_users, monkeypatch
):
    owner = two_users[1]
    monkeypatch.setattr(csvio, "MAX_IMPORT_ROWS", 2)
    text = "trade_date,asset,direction,result,pnl\n" + "".join(
        "2026-09-0{},NQ,Long,Win,{}\n".format(i + 1, i) for i in range(3)
    )
    handle = _session_handle_for(owner)
    r = _call(client, handle, "POST", "/v1/settings/import", {"csv": text})
    assert r.status_code == 422
    assert r.json() == {"detail": [{"field": "csv", "problem": "too_many_rows"}]}
    assert (
        _call(client, handle, "GET", "/v1/settings").json()["data"]["trade_count"] == 0
    )


def test_import_errors_never_echo_the_file(client, two_users):
    owner = two_users[1]
    text = "trade_date,asset\nSECRET-NOTE,NQ\n"
    body = _call(
        client, _session_handle_for(owner), "POST", "/v1/settings/import", {"csv": text}
    ).json()
    assert body["inserted"] == 0
    assert "SECRET-NOTE" not in json.dumps(body)


def test_import_errors_are_capped(client, two_users, monkeypatch):
    owner = two_users[1]
    monkeypatch.setattr(
        csvio,
        "import_trades_csv_text",
        lambda text, user_id: (0, 0, ["Row failed."] * 500),
    )
    body = _call(
        client,
        _session_handle_for(owner),
        "POST",
        "/v1/settings/import",
        {"csv": "a\n"},
    ).json()
    assert len(body["errors"]) == 20


@pytest.mark.parametrize(
    "payload",
    [{"csv": ""}, {"csv": 7}, {"file": "x"}, {}, {"csv": "a\n", "user_id": 1}],
)
def test_the_import_body_is_a_strict_allowlist(client, two_users, payload):
    r = _call(
        client,
        _session_handle_for(two_users[1]),
        "POST",
        "/v1/settings/import",
        payload,
    )
    assert r.status_code == 422


# ── destructive routes ─────────────────────────────────────────────────────

WRONG_CONFIRMATIONS = [
    "delete",
    "DELETE ",
    " DELETE",
    "DELETE MY  ACCOUNT",
    "delete my account",
    "DELETE MY ACCOUNT ",
    "",
    None,
    1,
    ["DELETE"],
]


@pytest.mark.parametrize(
    "path, phrase",
    [
        ("/v1/settings/delete-trades", "DELETE"),
        ("/v1/settings/delete-account", "DELETE MY ACCOUNT"),
    ],
)
@pytest.mark.parametrize("confirm", WRONG_CONFIRMATIONS)
def test_a_wrong_confirmation_is_422_and_deletes_nothing(
    client, two_users, monkeypatch, path, phrase, confirm
):
    if confirm == phrase:
        pytest.skip("the exact phrase is the success case")
    called = []
    monkeypatch.setattr(
        settings_router, "delete_all_trades_and_objects", lambda u: called.append(u)
    )
    monkeypatch.setattr(
        settings_router, "delete_account_and_objects", lambda u: called.append(u)
    )
    r = _call(
        client, _session_handle_for(two_users[1]), "POST", path, {"confirm": confirm}
    )
    assert r.status_code == 422
    assert called == []


@pytest.mark.parametrize(
    "path, payload",
    [
        ("/v1/settings/delete-trades", {"confirm": "DELETE", "user_id": 1}),
        ("/v1/settings/delete-account", {"confirm": "DELETE MY ACCOUNT", "owner": 1}),
        ("/v1/settings/delete-trades", {}),
    ],
)
def test_the_destructive_bodies_are_strict_allowlists(
    client, two_users, monkeypatch, path, payload
):
    called = []
    monkeypatch.setattr(
        settings_router, "delete_all_trades_and_objects", lambda u: called.append(u)
    )
    monkeypatch.setattr(
        settings_router, "delete_account_and_objects", lambda u: called.append(u)
    )
    r = _call(client, _session_handle_for(two_users[1]), "POST", path, payload)
    assert r.status_code == 422
    assert called == []


def test_delete_trades_runs_for_the_session_owner(client, two_users, monkeypatch):
    first, second = two_users
    seen = []
    monkeypatch.setattr(
        settings_router,
        "delete_all_trades_and_objects",
        lambda u: seen.append(u) or DeletionOutcome(3, 0, 0, False),
    )
    r = _call(
        client,
        _session_handle_for(second),
        "POST",
        "/v1/settings/delete-trades",
        {"confirm": "DELETE"},
    )
    assert r.status_code == 200
    assert r.json() == {"deleted": 3}
    assert seen == [second]


@pytest.mark.parametrize(
    "path, phrase",
    [
        ("/v1/settings/delete-trades", "DELETE"),
        ("/v1/settings/delete-account", "DELETE MY ACCOUNT"),
    ],
)
@pytest.mark.parametrize("remaining, unresolvable", [(2, 1), (1, 0), (0, 3)])
def test_a_blocked_cleanup_is_503_with_the_split_and_never_a_success(
    client, two_users, monkeypatch, path, phrase, remaining, unresolvable
):
    blocked = DeletionOutcome(0, remaining, unresolvable, True)
    monkeypatch.setattr(
        settings_router, "delete_all_trades_and_objects", lambda u: blocked
    )
    monkeypatch.setattr(
        settings_router, "delete_account_and_objects", lambda u: blocked
    )
    handle = _session_handle_for(two_users[1])
    r = _call(client, handle, "POST", path, {"confirm": phrase})
    assert r.status_code == 503
    assert r.json() == {
        "detail": {
            "error": "screenshot_cleanup_failed",
            "remaining": remaining,
            "unresolvable": unresolvable,
        }
    }
    # The session still works: a blocked account deletion deleted nothing.
    assert _call(client, handle, "GET", "/v1/settings").status_code == 200


def test_a_real_blocked_bulk_delete_leaves_every_trade(client, two_users, monkeypatch):
    owner = two_users[1]
    sample_data.load_sample_trades(owner)
    monkeypatch.setattr(
        storage,
        "delete_trade_objects",
        lambda u, t: ObjectCleanup(deleted=[], failed=["k"], skipped=[]),
    )
    handle = _session_handle_for(owner)
    r = _call(
        client, handle, "POST", "/v1/settings/delete-trades", {"confirm": "DELETE"}
    )
    assert r.status_code == 503
    body = _call(client, handle, "GET", "/v1/settings").json()
    assert body["data"]["trade_count"] == sample_data.SAMPLE_COUNT


def test_account_deletion_is_204_and_the_session_no_longer_works(
    client, two_users, monkeypatch
):
    first, owner = two_users
    sample_data.load_sample_trades(owner)
    monkeypatch.setattr(
        storage,
        "delete_trade_objects",
        lambda u, t: ObjectCleanup(deleted=[], failed=[], skipped=[]),
    )
    handle = _session_handle_for(owner)
    other = _session_handle_for(first)
    r = _call(
        client,
        handle,
        "POST",
        "/v1/settings/delete-account",
        {"confirm": "DELETE MY ACCOUNT"},
    )
    assert r.status_code == 204
    assert r.content == b""
    assert _call(client, handle, "GET", "/v1/settings").status_code == 401
    # The other account is untouched and still signed in.
    assert _call(client, other, "GET", "/v1/settings").status_code == 200


def test_a_missing_account_is_404(client, two_users, monkeypatch):
    monkeypatch.setattr(
        settings_router,
        "delete_account_and_objects",
        lambda u: DeletionOutcome(0, 0, 0, False),
    )
    r = _call(
        client,
        _session_handle_for(two_users[1]),
        "POST",
        "/v1/settings/delete-account",
        {"confirm": "DELETE MY ACCOUNT"},
    )
    assert r.status_code == 404
    assert r.json() == {"detail": "Not Found"}
