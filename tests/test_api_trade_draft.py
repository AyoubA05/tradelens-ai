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
from src.tradelens.api.routers.trades import _clear_draft
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
    body = dict(body)
    if "expected_revision" not in body:
        current = client.get(DRAFT_PATH, headers=_get_headers(handle))
        assert current.status_code == 200
        body["expected_revision"] = current.json()["revision"]
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
    body = json.dumps(
        {"asset": "NQ", "expected_revision": 0}, separators=(",", ":")
    ).encode()
    r = client.put(DRAFT_PATH, content=body, headers={"X-TL-Session-Handle": handle})
    assert r.status_code == 401


def test_put_a_tampered_body_fails_the_signature(client, website_session_handle):
    _, handle = website_session_handle
    signed = json.dumps(
        {"asset": "NQ", "expected_revision": 0}, separators=(",", ":")
    ).encode()
    tampered = json.dumps(
        {"asset": "MNQ", "expected_revision": 0}, separators=(",", ":")
    ).encode()
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
    assert r.json()["draft"] is None
    assert r.json()["revision"] == 0


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
    assert r.json()["draft"] is None


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
    signed = json.dumps(
        {"asset": "NQ", "expected_revision": 0}, separators=(",", ":")
    ).encode()
    tampered = json.dumps(
        {"asset": "NQ", "notes": "sneaky", "expected_revision": 0},
        separators=(",", ":"),
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


def test_the_browser_cannot_forge_worker_owned_suggestion_metadata(
    client, website_session_handle
):
    """An allowed key proves provenance, not the suggestion allowlist."""
    _, handle = website_session_handle
    suggestion = {"value": "ES", "confidence": 0.99, "autocheck": True}

    response = _put(
        client,
        handle,
        {
            "asset": "NQ",
            "ai_suggestions": {"asset": suggestion},
            "ai_suggestions_screenshot_id": 123,
        },
    )

    assert response.status_code == 422


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


# ------------------------------------------------- the draft's end of life (F1)


def _create_headers(handle, body: bytes, *, path="/v1/trades"):
    ts = str(int(time.time()))
    sig = sign_request(SECRET, ts, "POST", path, "", body)
    return {
        "Content-Type": "application/json",
        "X-TL-Signature": f"v1={ts}:{sig}",
        "X-TL-Session-Handle": handle,
    }


def _create_body(**overrides) -> dict:
    body = {
        "trade_date": "2026-08-10",
        "entry_time": "09:30",
        "asset": "NQ",
        "direction": "Long",
        "entry_price": 100.0,
        "stop_price": 95.0,
        "tp_price": 115.0,
        "result": "Win",
        "pnl": 250.0,
    }
    body.update(overrides)
    return body


def _create_trade(client, handle, body: dict):
    payload = json.dumps(body, separators=(",", ":")).encode()
    return client.post(
        "/v1/trades", content=payload, headers=_create_headers(handle, payload)
    )


def test_journaling_a_trade_ends_the_draft(client, website_session_handle):
    """A journaled trade leaves no draft behind for the next one to inherit.

    Without `_clear_draft` in the create route the draft survives the create,
    and the browser's mount-time prefill fills any still-empty field from it —
    so the NEXT New Trade opens carrying this trade's asset, entry time and
    prices. This asserts the sequence directly: save a draft, create the
    trade, re-read the draft the next form would load.
    """
    owner, handle = website_session_handle
    _put(
        client,
        handle,
        {
            "asset": "NQ",
            "entry_time": "09:45",
            "entry_price": 21000.0,
            "stop_price": 20950.0,
            "trade_process_notes": "waited for the sweep",
        },
    )
    assert client.get(DRAFT_PATH, headers=_get_headers(handle)).json()["draft"]

    created = _create_trade(client, handle, _create_body())
    assert created.status_code == 201

    # What the next New Trade form would load: nothing.
    r = client.get(DRAFT_PATH, headers=_get_headers(handle))
    assert r.status_code == 200
    assert r.json()["draft"] is None
    assert drafts.get_draft(owner) is None


def test_a_stale_autosave_cannot_recreate_a_draft_after_create(
    client, website_session_handle
):
    """A PUT already in flight when submit begins must lose to create."""
    _, handle = website_session_handle
    first = _put(client, handle, {"asset": "NQ", "entry_time": "09:30"})
    assert first.status_code == 200
    stale_revision = first.json().get("revision")
    assert isinstance(stale_revision, int)

    created = _create_trade(client, handle, _create_body())
    assert created.status_code == 201

    late = _put(
        client,
        handle,
        {
            "asset": "NQ",
            "entry_time": "09:30",
            "expected_revision": stale_revision,
        },
    )
    assert late.status_code == 409
    after = client.get(DRAFT_PATH, headers=_get_headers(handle)).json()
    assert after["draft"] is None
    assert after["revision"] > stale_revision


def test_a_new_form_can_save_after_the_previous_draft_was_retired(
    client, website_session_handle
):
    """The tombstone blocks old writes without locking out a new form."""
    _, handle = website_session_handle
    first = _put(client, handle, {"asset": "NQ"})
    assert first.status_code == 200
    assert _create_trade(client, handle, _create_body()).status_code == 201

    empty = client.get(DRAFT_PATH, headers=_get_headers(handle)).json()
    assert empty["draft"] is None
    replacement = _put(
        client,
        handle,
        {"asset": "ES", "expected_revision": empty["revision"]},
    )
    assert replacement.status_code == 200
    assert replacement.json()["draft"]["asset"] == "ES"


def test_a_duplicate_submit_also_ends_the_draft(client, website_session_handle):
    """The 200/`duplicate_of` branch clears too — that trade exists as well."""
    _, handle = website_session_handle
    body = _create_body(trade_date="2026-08-11")
    assert _create_trade(client, handle, body).status_code == 201
    _put(client, handle, {"asset": "NQ", "entry_price": 21000.0})

    again = _create_trade(client, handle, body)
    assert again.status_code == 200
    assert again.json()["duplicate_of"] is not None
    assert client.get(DRAFT_PATH, headers=_get_headers(handle)).json()["draft"] is None


def test_one_owner_s_create_does_not_clear_another_s_draft(client, two_users):
    """Clearing is owner-scoped, like every other draft operation."""
    trader_a, trader_b = two_users
    drafts.save_draft(trader_a, {"asset": "NQ"})
    drafts.save_draft(trader_b, {"asset": "ES", "entry_price": 5000.0})
    _clear_draft(trader_a)
    assert drafts.get_draft(trader_b) == {"asset": "ES", "entry_price": 5000.0}


# ------------------------- an autosave may not destroy the worker's writes (F2)


def test_an_autosave_cannot_clobber_written_suggestions(client, website_session_handle):
    """The interleaving that made a paid vision reading unrecoverable.

    Worker writes suggestions; a PUT that was already in flight (and, like
    every autosave body, does not mention `ai_suggestions`) lands after it.
    With a wholesale replace both the suggestions and their provenance key
    vanish, the poll then answers `superseded` forever — the enqueue
    idempotency key is the screenshot, so the same succeeded job comes back
    on every retry and nothing can re-read that chart.
    """
    owner, handle = website_session_handle
    drafts.save_draft(owner, {"asset": "NQ"})
    drafts.save_draft(
        owner,
        {
            "asset": "NQ",
            "ai_suggestions": {
                "direction": {"value": "Long", "confidence": 0.9, "autocheck": True}
            },
            "ai_suggestions_screenshot_id": 77,
        },
    )

    # The in-flight autosave: the trader kept typing, no suggestion keys.
    r = _put(client, handle, {"asset": "NQ", "notes": "typed while it ran"})
    assert r.status_code == 200

    stored = drafts.get_draft(owner)
    assert stored["notes"] == "typed while it ran"
    assert stored["ai_suggestions"]["direction"]["value"] == "Long"
    assert stored["ai_suggestions_screenshot_id"] == 77


def test_clearing_the_draft_still_clears_suggestions(client, website_session_handle):
    """Preserving worker keys must not make them immortal.

    `delete_draft` removes the row, so the merge above cannot resurrect a
    suggestion set past the trade it belonged to.
    """
    owner, _ = website_session_handle
    drafts.save_draft(
        owner, {"asset": "NQ", "ai_suggestions_screenshot_id": 5, "ai_suggestions": {}}
    )
    drafts.delete_draft(owner)
    drafts.save_draft(owner, {"asset": "ES"})
    assert drafts.get_draft(owner) == {"asset": "ES"}


# ------------------------------- a stored draft that no longer validates (F3)


def test_a_stored_draft_the_model_no_longer_accepts_reads_as_no_draft(
    client, website_session_handle
):
    """A renamed or removed draft field must not 500 every stored draft.

    `TradeDraftPayload` is `extra="forbid"`, and a draft stored under an older
    shape is re-validated with today's model on every read. Unguarded, that is
    a 500 the relay swallows into nothing, so autosave appears to stop working
    with no signal and the row stays poisoned forever. Degrading to "no draft"
    lets the next autosave replace it.
    """
    owner, handle = website_session_handle
    drafts.save_draft(owner, {"asset": "NQ", "a_field_this_model_removed": "x"})
    r = client.get(DRAFT_PATH, headers=_get_headers(handle))
    assert r.status_code == 200
    assert r.json()["draft"] is None
