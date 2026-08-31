"""`PUT /v1/trades/draft` and `GET /v1/trades/draft`.

Mirrors the create endpoint's tests (`tests/test_api_trades.py`) for the
signing discipline, and adds the property that matters most for this
endpoint specifically: no number of draft saves ever creates a `trades` row,
and no derived field can reach a draft.
"""

from __future__ import annotations

import json
import time

import pytest
from fastapi.testclient import TestClient

from src.tradelens.api.app import create_app
from src.tradelens.api.schemas.trades import (
    CREATABLE_TRADE_FIELDS,
    DRAFT_TRADE_FIELDS,
    SERVER_OWNED_ON_CREATE,
)
from src.tradelens.api.security import sign_request
from src.tradelens.db.models import Trade
from src.tradelens.db.session import SessionLocal
from src.tradelens.services import drafts

SECRET = "test-service-secret-value-at-least-32-bytes"
DRAFT_PATH = "/v1/trades/draft"


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


def _get_headers(handle, *, path=DRAFT_PATH):
    ts = str(int(time.time()))
    sig = sign_request(SECRET, ts, "GET", path, "", b"")
    return {"X-TL-Signature": f"v1={ts}:{sig}", "X-TL-Session-Handle": handle}


def _put_headers(handle, body: bytes, *, path=DRAFT_PATH):
    ts = str(int(time.time()))
    sig = sign_request(SECRET, ts, "PUT", path, "", body)
    return {
        "Content-Type": "application/json",
        "X-TL-Signature": f"v1={ts}:{sig}",
        "X-TL-Session-Handle": handle,
    }


def _put(client, handle, body: dict):
    payload = json.dumps(body, separators=(",", ":")).encode()
    return client.put(
        DRAFT_PATH, content=payload, headers=_put_headers(handle, payload)
    )


def _trades_row_count() -> int:
    db = SessionLocal()
    try:
        return db.query(Trade).count()
    finally:
        db.close()


# ------------------------------------------------------------- Lock 1 / auth


def test_get_unsigned_request_is_refused(client, website_session_handle):
    _, handle = website_session_handle
    r = client.get(DRAFT_PATH, headers={"X-TL-Session-Handle": handle})
    assert r.status_code == 401


def test_get_without_a_session_is_refused(client):
    ts = str(int(time.time()))
    sig = sign_request(SECRET, ts, "GET", DRAFT_PATH, "", b"")
    r = client.get(DRAFT_PATH, headers={"X-TL-Signature": f"v1={ts}:{sig}"})
    assert r.status_code == 401


def test_put_unsigned_request_is_refused(client, website_session_handle):
    _, handle = website_session_handle
    body = json.dumps({"asset": "NQ"}, separators=(",", ":")).encode()
    r = client.put(DRAFT_PATH, content=body, headers={"X-TL-Session-Handle": handle})
    assert r.status_code == 401


def test_put_a_tampered_body_fails_the_signature(client, website_session_handle):
    _, handle = website_session_handle
    signed = json.dumps({"asset": "NQ"}, separators=(",", ":")).encode()
    tampered = json.dumps({"asset": "MNQ"}, separators=(",", ":")).encode()
    r = client.put(DRAFT_PATH, content=tampered, headers=_put_headers(handle, signed))
    assert r.status_code == 401


# ------------------------------------------------------------------ behavior


def test_draft_round_trips(client, website_session_handle):
    _, handle = website_session_handle
    body = {"asset": "NQ", "notes": "still deciding on the stop", "direction": "Long"}
    r = _put(client, handle, body)
    assert r.status_code == 200
    assert r.json()["draft"]["asset"] == "NQ"
    assert r.json()["draft"]["notes"] == "still deciding on the stop"

    r = client.get(DRAFT_PATH, headers=_get_headers(handle))
    assert r.status_code == 200
    assert r.json()["draft"]["asset"] == "NQ"
    assert r.json()["draft"]["direction"] == "Long"


def test_owner_with_no_draft_gets_null(client, website_session_handle):
    _, handle = website_session_handle
    r = client.get(DRAFT_PATH, headers=_get_headers(handle))
    assert r.status_code == 200
    assert r.json() == {"draft": None}


def test_saving_twice_supersedes(client, website_session_handle):
    _, handle = website_session_handle
    _put(client, handle, {"asset": "NQ"})
    _put(client, handle, {"asset": "MNQ", "notes": "changed my mind"})

    r = client.get(DRAFT_PATH, headers=_get_headers(handle))
    assert r.json()["draft"]["asset"] == "MNQ"
    assert r.json()["draft"]["notes"] == "changed my mind"


def test_a_second_owner_s_draft_is_invisible(client, two_users):
    """The route-level analog of the service-level isolation test.

    Builds a second live session directly (mirroring the `website_session`
    fixture, which only wires up trader_a) so trader_b's authenticated GET
    is exercised end-to-end rather than only through the service.
    """
    import datetime as dt
    import hashlib
    import secrets

    from sqlalchemy import text as sa_text

    from src.tradelens.services import auth_sessions
    from src.tradelens.services import drafts as drafts_service

    user_a, user_b = two_users
    token = secrets.token_urlsafe(32)
    now = dt.datetime.now(dt.timezone.utc)
    digest = hashlib.sha256((auth_sessions.WEBSITE_DOMAIN + token).encode()).hexdigest()
    db = SessionLocal()
    try:
        db.execute(
            sa_text(
                "INSERT INTO auth_sessions (token_hash, user_id, created_at, "
                "expires_at, last_seen_at, surface) VALUES (:h,:u,:c,:e,:l,:s)"
            ),
            {
                "h": digest,
                "u": user_b,
                "c": now,
                "e": now + dt.timedelta(hours=12),
                "l": now,
                "s": auth_sessions.SURFACE_WEBSITE,
            },
        )
        db.commit()
    finally:
        db.close()
    handle_b = hashlib.sha256(
        (auth_sessions.WEBSITE_DOMAIN + token).encode()
    ).hexdigest()

    drafts_service.save_draft(user_a, {"asset": "NQ"})

    r = client.get(DRAFT_PATH, headers=_get_headers(handle_b))
    assert r.json() == {"draft": None}


def test_no_number_of_draft_saves_creates_a_trades_row(client, website_session_handle):
    _, handle = website_session_handle
    before = _trades_row_count()
    for i in range(5):
        r = _put(client, handle, {"asset": f"NQ{i}", "notes": f"attempt {i}"})
        assert r.status_code == 200
    after = _trades_row_count()
    assert after == before == 0


def test_derived_fields_are_rejected(client, website_session_handle):
    _, handle = website_session_handle
    for field, value in [
        ("session", "NY AM"),
        ("killzone", "New York AM"),
        ("strategy_used", "ICT 2022"),
        ("asset_class", "Futures"),
        ("day_of_week", "Monday"),
        ("rr_planned", 2.0),
        ("trade_hash", "deadbeef"),
        ("user_id", 999),
        ("id", 1),
        ("create_idempotency_key", "x"),
    ]:
        r = _put(client, handle, {"asset": "NQ", field: value})
        assert r.status_code == 422, f"{field} should have been rejected"


def test_body_tampered_request_fails_lock_1(client, website_session_handle):
    _, handle = website_session_handle
    signed = json.dumps({"asset": "NQ"}, separators=(",", ":")).encode()
    tampered = json.dumps(
        {"asset": "NQ", "notes": "sneaky"}, separators=(",", ":")
    ).encode()
    r = client.put(DRAFT_PATH, content=tampered, headers=_put_headers(handle, signed))
    assert r.status_code == 401


# ---------------------------------------------------------- allowlist contract


def test_draft_allowlist_is_a_subset_of_the_create_allowlist():
    assert DRAFT_TRADE_FIELDS <= CREATABLE_TRADE_FIELDS


def test_draft_allowlist_is_disjoint_from_server_owned_fields():
    assert DRAFT_TRADE_FIELDS.isdisjoint(SERVER_OWNED_ON_CREATE)


# --------------------------------------------- the wire-level suggestion filter


def test_a_derived_field_cannot_be_suggested_on_the_wire(
    client, website_session_handle
):
    """`ai_suggestions` keys are checked against the autofill allowlist here too.

    The service-layer filter (`trade_autofill.filter_suggestions`) is the
    load-bearing one, but the report advertises this second, wire-level copy
    explicitly, so it is pinned: deleting
    `TradeDraftPayload._suggestions_must_be_suggestable` makes this pass a
    `strategy_used` suggestion straight through.
    """
    _, handle = website_session_handle
    suggestion = {"value": "ICT 2022", "confidence": 0.9, "autocheck": False}
    r = _put(
        client, handle, {"asset": "NQ", "ai_suggestions": {"strategy_used": suggestion}}
    )
    assert r.status_code == 422


def test_a_stored_derived_suggestion_cannot_round_trip_through_get(
    client, website_session_handle
):
    """Even a draft written past the service filter cannot be read back.

    `drafts.save_draft` is called directly here precisely because the point is
    what happens when something upstream stored a suggestion it should not
    have: the response model refuses to shape it, so a derived field never
    reaches the browser as a reviewable suggestion.
    """
    owner, handle = website_session_handle
    drafts.save_draft(
        owner,
        {
            "asset": "NQ",
            "ai_suggestions": {
                "strategy_used": {
                    "value": "ICT 2022",
                    "confidence": 0.9,
                    "autocheck": False,
                }
            },
        },
    )
    r = client.get(DRAFT_PATH, headers=_get_headers(handle))
    assert r.status_code != 200 or "strategy_used" not in r.text
