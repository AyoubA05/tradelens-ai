"""`GET /v1/trades` and `GET /v1/trades/{id}`.

Mirrors tests/test_api_overview.py: the owner comes from the session row, the
period is validated server-side even though the HMAC already covers the
query, and a second trader's rows are never reachable — a cross-owner trade
must 404, byte-identical to a genuinely missing one, never 403.
"""

from __future__ import annotations

import contextlib
import json
import time

import pytest
from fastapi.testclient import TestClient

from src.tradelens.api.app import create_app
from src.tradelens.api.security import sign_request
from src.tradelens.services import trade_service

SECRET = "test-service-secret-value-at-least-32-bytes"
LIST_PATH = "/v1/trades"
QUERY = "from=2026-08-01&to=2026-08-31"


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


def _headers(handle, *, query=QUERY, path=LIST_PATH):
    ts = str(int(time.time()))
    sig = sign_request(SECRET, ts, "GET", path, query, b"")
    return {"X-TL-Signature": f"v1={ts}:{sig}", "X-TL-Session-Handle": handle}


def _create(user_id, **overrides):
    data = {"asset": "NQ", "trade_date": "2026-08-10"}
    data.update(overrides)
    return trade_service.create_trade(data, user_id=user_id)


# ---------------------------------------------------------------- GET /v1/trades


def test_list_unsigned_request_is_refused(client, website_session_handle):
    _, handle = website_session_handle
    r = client.get(f"{LIST_PATH}?{QUERY}", headers={"X-TL-Session-Handle": handle})
    assert r.status_code == 401


def test_list_request_without_a_session_is_refused(client):
    ts = str(int(time.time()))
    sig = sign_request(SECRET, ts, "GET", LIST_PATH, QUERY, b"")
    r = client.get(f"{LIST_PATH}?{QUERY}", headers={"X-TL-Signature": f"v1={ts}:{sig}"})
    assert r.status_code == 401


def test_list_a_tampered_query_fails_the_signature(client, website_session_handle):
    _, handle = website_session_handle
    r = client.get(
        f"{LIST_PATH}?from=1990-01-01&to=2099-01-01", headers=_headers(handle)
    )
    assert r.status_code == 401


def test_list_returns_the_owner_s_trades(client, website_session_handle):
    user_id, handle = website_session_handle
    _create(user_id, trade_date="2026-08-10")
    r = client.get(f"{LIST_PATH}?{QUERY}", headers=_headers(handle))
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert len(body["trades"]) == 1


def test_list_never_returns_another_owner_s_rows(
    client, website_session_handle, two_users
):
    user_id, handle = website_session_handle
    other = next(u for u in two_users if u != user_id)
    _create(other, trade_date="2026-08-10")

    r = client.get(f"{LIST_PATH}?{QUERY}", headers=_headers(handle))
    body = r.json()
    assert body["total"] == 0
    assert body["trades"] == []


def test_list_invalid_period_is_rejected_with_422(client, website_session_handle):
    _, handle = website_session_handle
    bad = "from=not-a-date&to=2026-08-31"
    r = client.get(f"{LIST_PATH}?{bad}", headers=_headers(handle, query=bad))
    assert r.status_code == 422


def test_list_reversed_period_is_rejected(client, website_session_handle):
    _, handle = website_session_handle
    bad = "from=2026-08-31&to=2026-08-01"
    r = client.get(f"{LIST_PATH}?{bad}", headers=_headers(handle, query=bad))
    assert r.status_code == 422


def test_list_limit_is_clamped_not_honoured(client, website_session_handle):
    user_id, handle = website_session_handle
    for i in range(3):
        _create(user_id, trade_date=f"2026-08-{i + 1:02d}")
    q = f"{QUERY}&limit=1000"
    r = client.get(f"{LIST_PATH}?{q}", headers=_headers(handle, query=q))
    assert r.status_code == 200
    assert r.json()["limit"] == 100


def test_list_response_is_not_cacheable(client, website_session_handle):
    _, handle = website_session_handle
    r = client.get(f"{LIST_PATH}?{QUERY}", headers=_headers(handle))
    assert "no-store" in r.headers.get("cache-control", "")


def test_list_killzone_renders_the_label_not_the_raw_key(
    client, website_session_handle
):
    user_id, handle = website_session_handle
    _create(user_id, trade_date="2026-08-10", killzone="ny_am")
    r = client.get(f"{LIST_PATH}?{QUERY}", headers=_headers(handle))
    assert r.json()["trades"][0]["killzone"] == "New York AM"


def test_list_handler_return_annotation_is_the_typed_model():
    spec = create_app().openapi()
    ref = spec["paths"]["/v1/trades"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]["$ref"]
    assert ref.endswith("/TradeListResponse")


# ------------------------------------------------------------ GET /v1/trades/{id}


def test_detail_returns_the_owner_s_trade(client, website_session_handle):
    user_id, handle = website_session_handle
    trade = _create(user_id, trade_date="2026-08-10", killzone="ny_am")
    path = f"/v1/trades/{trade.id}"
    r = client.get(path, headers=_headers(handle, query="", path=path))
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == trade.id
    assert body["killzone"] == "New York AM"
    assert body["screenshots"] == []


def test_detail_another_owner_s_trade_is_404(client, website_session_handle, two_users):
    user_id, handle = website_session_handle
    other = next(u for u in two_users if u != user_id)
    trade = _create(other, trade_date="2026-08-10")

    path = f"/v1/trades/{trade.id}"
    r = client.get(path, headers=_headers(handle, query="", path=path))
    assert r.status_code == 404


def test_detail_missing_trade_is_404_byte_identical_to_cross_owner(
    client, website_session_handle, two_users
):
    """A 403 would confirm the row exists — this endpoint must never emit one."""
    user_id, handle = website_session_handle
    other = next(u for u in two_users if u != user_id)
    other_trade = _create(other, trade_date="2026-08-10")

    cross_owner_path = f"/v1/trades/{other_trade.id}"
    cross_owner = client.get(
        cross_owner_path, headers=_headers(handle, query="", path=cross_owner_path)
    )

    missing_path = "/v1/trades/999999"
    missing = client.get(
        missing_path, headers=_headers(handle, query="", path=missing_path)
    )

    assert cross_owner.status_code == 404
    assert missing.status_code == 404
    assert cross_owner.content == missing.content


def test_detail_no_presigned_url_for_a_trade_the_caller_does_not_own(
    client, website_session_handle, two_users, monkeypatch
):
    user_id, handle = website_session_handle
    other = next(u for u in two_users if u != user_id)
    trade = _create(other, trade_date="2026-08-10")

    calls = []

    def _spy(owner, screenshot_id):
        calls.append((owner, screenshot_id))
        return "https://example.invalid/should-not-be-called"

    from src.tradelens.api import storage as storage_module

    monkeypatch.setattr(storage_module, "presign_download", _spy)

    path = f"/v1/trades/{trade.id}"
    r = client.get(path, headers=_headers(handle, query="", path=path))
    assert r.status_code == 404
    assert calls == []


# ------------------------------------------------------------ PATCH /v1/trades/{id}


def _write_headers(handle, method, path, body: bytes):
    """Sign a mutating request. The HMAC covers sha256(body), so the payload
    is as tamper-evident as the path and query."""
    ts = str(int(time.time()))
    sig = sign_request(SECRET, ts, method, path, "", body)
    return {
        "X-TL-Signature": f"v1={ts}:{sig}",
        "X-TL-Session-Handle": handle,
        "Content-Type": "application/json",
    }


def _patch(client, handle, trade_id, payload):
    path = f"/v1/trades/{trade_id}"
    body = json.dumps(payload).encode()
    return client.patch(
        path, content=body, headers=_write_headers(handle, "PATCH", path, body)
    )


def _read_row(trade_id):
    """Read a row straight from the database, bypassing every service."""
    from src.tradelens.db.models import Trade
    from src.tradelens.db.session import SessionLocal

    db = SessionLocal()
    try:
        row = db.query(Trade).filter(Trade.id == trade_id).first()
        if row is None:
            return None
        return {c.key: getattr(row, c.key) for c in Trade.__table__.columns}
    finally:
        db.close()


@contextlib.contextmanager
def _captured_sql():
    """Every statement the engine executes, so a test can assert on the
    *shape* of the write rather than only on its observable effect."""
    from sqlalchemy import event

    from src.tradelens.db import session as db_session

    seen = []

    def _record(conn, cursor, statement, parameters, context, executemany):
        seen.append((statement, parameters))

    event.listen(db_session.engine, "before_cursor_execute", _record)
    try:
        yield seen
    finally:
        event.remove(db_session.engine, "before_cursor_execute", _record)


def _trade_updates(seen):
    return [
        (stmt, params)
        for stmt, params in seen
        if stmt.lstrip().upper().startswith("UPDATE TRADES")
    ]


def test_patch_unsigned_request_is_refused(client, website_session_handle):
    user_id, handle = website_session_handle
    trade = _create(user_id)
    path = f"/v1/trades/{trade.id}"
    body = json.dumps({"notes": "x", "expected_updated_at": trade.updated_at}).encode()
    r = client.patch(path, content=body, headers={"X-TL-Session-Handle": handle})
    assert r.status_code == 401
    assert _read_row(trade.id)["notes"] is None


def test_patch_a_tampered_body_fails_the_signature(client, website_session_handle):
    """The HMAC covers sha256(body): swapping the payload after signing must
    fail Lock 1, not merely be rejected by validation."""
    user_id, handle = website_session_handle
    trade = _create(user_id)
    path = f"/v1/trades/{trade.id}"
    signed = json.dumps(
        {"notes": "a", "expected_updated_at": trade.updated_at}
    ).encode()
    sent = json.dumps(
        {"notes": "tampered", "expected_updated_at": trade.updated_at}
    ).encode()
    r = client.patch(
        path, content=sent, headers=_write_headers(handle, "PATCH", path, signed)
    )
    assert r.status_code == 401
    assert _read_row(trade.id)["notes"] is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("trade_date", "2026-08-20"),
        ("asset", "ES"),
        ("session", "London"),
        ("setup_type", "Turtle Soup"),
        ("timeframe", "M5"),
        ("direction", "Short"),
        ("rr_realized", 2.5),
        ("risk_amount", 120.0),
        ("followed_rules", 1),
        ("killzone", "London Open"),
        ("htf_bias", "Bearish"),
        ("notes", "Chased the entry."),
        ("mistake_tags", "fomo,late-entry"),
    ],
)
def test_patch_every_editable_field_round_trips(
    client, website_session_handle, field, value
):
    user_id, handle = website_session_handle
    trade = _create(user_id)
    r = _patch(
        client,
        handle,
        trade.id,
        {field: value, "expected_updated_at": trade.updated_at},
    )
    assert r.status_code == 200, r.text
    assert r.json()[field] == value


def test_patch_result_and_pnl_round_trip_together(client, website_session_handle):
    user_id, handle = website_session_handle
    trade = _create(user_id)
    r = _patch(
        client,
        handle,
        trade.id,
        {"pnl": 250.0, "result": "Win", "expected_updated_at": trade.updated_at},
    )
    assert r.status_code == 200, r.text
    assert r.json()["pnl"] == 250.0
    assert r.json()["result"] == "Win"


def test_patch_editing_pnl_rederives_result(client, website_session_handle):
    """P&L is the fact; the label describes it. A row may never contradict
    itself, so a new P&L re-derives the outcome rather than being vetoed by
    the label that described the old value."""
    user_id, handle = website_session_handle
    trade = _create(user_id, pnl=100.0, result="Win")
    r = _patch(
        client,
        handle,
        trade.id,
        {"pnl": -40.0, "expected_updated_at": trade.updated_at},
    )
    assert r.status_code == 200, r.text
    assert r.json()["result"] == "Loss"
    assert _read_row(trade.id)["result"] == "Loss"


def test_patch_a_label_contradicting_the_stored_pnl_is_rejected(
    client, website_session_handle
):
    user_id, handle = website_session_handle
    trade = _create(user_id, pnl=100.0, result="Win")
    r = _patch(
        client,
        handle,
        trade.id,
        {"result": "Loss", "expected_updated_at": trade.updated_at},
    )
    assert r.status_code == 422
    assert _read_row(trade.id)["result"] == "Win"


@pytest.mark.parametrize(
    "field,value",
    [
        ("user_id", 999),
        ("trade_hash", "deadbeef"),
        ("is_sample", 1),
        ("created_at", "1999-01-01T00:00:00+00:00"),
        ("strategy_id", 7),
        ("id", 4242),
        ("trade_id", 4242),
        ("updated_at", "1999-01-01T00:00:00+00:00"),
        ("day_of_week", "Monday"),
        ("entry_price", 1.0),
        ("ai_grade", "A+"),
    ],
)
def test_patch_rejects_fields_outside_the_allowlist(
    client, website_session_handle, field, value
):
    """`extra="forbid"` on a POSITIVE allowlist: ownership and server-owned
    metadata are unreachable through HTTP input whatever the request says."""
    user_id, handle = website_session_handle
    trade = _create(user_id)
    before = _read_row(trade.id)
    r = _patch(
        client,
        handle,
        trade.id,
        {field: value, "expected_updated_at": trade.updated_at},
    )
    assert r.status_code == 422, r.text
    assert _read_row(trade.id) == before


def test_patch_requires_expected_updated_at(client, website_session_handle):
    user_id, handle = website_session_handle
    trade = _create(user_id)
    r = _patch(client, handle, trade.id, {"notes": "x"})
    assert r.status_code == 422
    assert _read_row(trade.id)["notes"] is None


def test_the_allowlist_and_the_models_editable_columns_agree():
    """The write surface is pinned in both directions.

    Adding a column to `Trade` must not silently widen what HTTP can write:
    a new column lands in neither set, so this test fails until someone
    deliberately files it as editable or as server-owned.
    """
    from src.tradelens.api.schemas.trades import (
        EDITABLE_TRADE_FIELDS,
        SERVER_OWNED_TRADE_COLUMNS,
    )
    from src.tradelens.db.models import Trade

    columns = {c.key for c in Trade.__table__.columns}
    assert (
        EDITABLE_TRADE_FIELDS <= columns
    ), "allowlist names a column that does not exist"
    assert EDITABLE_TRADE_FIELDS.isdisjoint(SERVER_OWNED_TRADE_COLUMNS)
    assert EDITABLE_TRADE_FIELDS | SERVER_OWNED_TRADE_COLUMNS == columns

    # The fields that must never be writable, named explicitly rather than
    # inferred, so a refactor of either set still trips this.
    for forbidden in (
        "user_id",
        "id",
        "trade_hash",
        "is_sample",
        "created_at",
        "updated_at",
        "strategy_id",
    ):
        assert forbidden in SERVER_OWNED_TRADE_COLUMNS
        assert forbidden not in EDITABLE_TRADE_FIELDS


def test_patch_another_owners_trade_is_404_and_leaves_it_untouched(
    client, website_session_handle, two_users
):
    user_id, handle = website_session_handle
    other = next(u for u in two_users if u != user_id)
    trade = _create(other, notes="theirs")
    before = _read_row(trade.id)

    with _captured_sql() as seen:
        r = _patch(
            client,
            handle,
            trade.id,
            {"notes": "mine now", "expected_updated_at": trade.updated_at},
        )

    assert r.status_code == 404
    assert _read_row(trade.id) == before
    assert _trade_updates(seen) == [], "no write may be attempted for another owner"


def test_patch_cross_owner_404_is_byte_identical_to_a_missing_trade(
    client, website_session_handle, two_users
):
    """A 403 would confirm the row exists for someone else."""
    user_id, handle = website_session_handle
    other = next(u for u in two_users if u != user_id)
    theirs = _create(other)
    stamp = theirs.updated_at

    cross = _patch(
        client, handle, theirs.id, {"notes": "x", "expected_updated_at": stamp}
    )
    missing = _patch(
        client, handle, 999999, {"notes": "x", "expected_updated_at": stamp}
    )

    assert cross.status_code == missing.status_code == 404
    assert cross.content == missing.content


def test_patch_with_a_stale_expected_updated_at_is_409_and_changes_nothing(
    client, website_session_handle
):
    user_id, handle = website_session_handle
    trade = _create(user_id, notes="original")
    before = _read_row(trade.id)

    r = _patch(
        client,
        handle,
        trade.id,
        {"notes": "clobbered", "expected_updated_at": "1999-01-01T00:00:00+00:00"},
    )

    assert r.status_code == 409
    assert r.json()["detail"]["current_updated_at"] == before["updated_at"]
    assert _read_row(trade.id) == before


def test_the_409_comes_from_a_single_conditional_updates_rowcount(
    client, website_session_handle
):
    """The concurrency decision is the rowcount of ONE conditional UPDATE.

    Reading the row, comparing `updated_at` in Python, then writing leaves a
    window in which another request commits in between — reintroducing the
    exact lost update the field exists to prevent. So the stale case must
    still ISSUE the write, and its predicate must carry all three of trade
    id, owner and expected timestamp.
    """
    user_id, handle = website_session_handle
    trade = _create(user_id, notes="original")

    with _captured_sql() as seen:
        r = _patch(
            client,
            handle,
            trade.id,
            {"notes": "clobbered", "expected_updated_at": "1999-01-01T00:00:00+00:00"},
        )

    assert r.status_code == 409
    updates = _trade_updates(seen)
    assert len(updates) == 1, "the write must be a single conditional statement"
    statement, params = updates[0]
    where = statement.upper().split("WHERE", 1)[1]
    for column in ("ID", "USER_ID", "UPDATED_AT"):
        assert column in where, f"the write predicate must carry {column}"
    bound = list(params.values()) if isinstance(params, dict) else list(params)
    assert trade.id in bound
    assert user_id in bound
    assert "1999-01-01T00:00:00+00:00" in bound


def test_a_fresh_expected_updated_at_from_the_previous_patch_succeeds(
    client, website_session_handle
):
    """Two sequential edits: the second must use the stamp the first returned."""
    user_id, handle = website_session_handle
    trade = _create(user_id)

    first = _patch(
        client,
        handle,
        trade.id,
        {"notes": "a", "expected_updated_at": trade.updated_at},
    )
    assert first.status_code == 200
    stamp = first.json()["updated_at"]
    assert stamp != trade.updated_at

    second = _patch(
        client, handle, trade.id, {"notes": "b", "expected_updated_at": stamp}
    )
    assert second.status_code == 200
    assert _read_row(trade.id)["notes"] == "b"

    replay = _patch(
        client, handle, trade.id, {"notes": "c", "expected_updated_at": stamp}
    )
    assert replay.status_code == 409
    assert _read_row(trade.id)["notes"] == "b"


def test_patch_an_omitted_field_is_untouched_but_an_explicit_null_clears_it(
    client, website_session_handle
):
    user_id, handle = website_session_handle
    trade = _create(user_id, notes="keep me", htf_bias="Bullish")

    r = _patch(
        client,
        handle,
        trade.id,
        {"htf_bias": None, "expected_updated_at": trade.updated_at},
    )
    assert r.status_code == 200
    row = _read_row(trade.id)
    assert row["notes"] == "keep me"
    assert row["htf_bias"] is None


def test_patch_response_is_the_typed_trade_detail_model():
    spec = create_app().openapi()
    operation = spec["paths"]["/v1/trades/{trade_id}"]["patch"]
    ok = operation["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
    assert ok.endswith("/TradeDetail")
    conflict = operation["responses"]["409"]["content"]["application/json"]["schema"][
        "$ref"
    ]
    assert conflict.endswith("/TradeConflictResponse")


# ----------------------------------------------------------- DELETE /v1/trades/{id}


def _delete(client, handle, trade_id):
    path = f"/v1/trades/{trade_id}"
    return client.delete(path, headers=_write_headers(handle, "DELETE", path, b""))


def _add_screenshot(trade_id, file_path):
    from src.tradelens.db.models import Screenshot
    from src.tradelens.db.session import SessionLocal

    db = SessionLocal()
    try:
        shot = Screenshot(trade_id=trade_id, file_path=file_path)
        db.add(shot)
        db.commit()
        return shot.id
    finally:
        db.close()


def _screenshot_rows(trade_id):
    from src.tradelens.db.models import Screenshot
    from src.tradelens.db.session import SessionLocal

    db = SessionLocal()
    try:
        return [
            row[0]
            for row in db.query(Screenshot.id)
            .filter(Screenshot.trade_id == trade_id)
            .all()
        ]
    finally:
        db.close()


class _CleanupSpy:
    """Stands in for `storage.delete_trade_objects` so a test can assert on the
    calls that were made, not merely on the row that survived."""

    def __init__(self, failed=()):
        self.calls = []
        self._failed = list(failed)

    def __call__(self, user_id, trade_id):
        from src.tradelens.api.storage import ObjectCleanup

        self.calls.append((user_id, trade_id))
        return ObjectCleanup(deleted=[], failed=list(self._failed), skipped=[])


def test_delete_unsigned_request_is_refused(client, website_session_handle):
    user_id, handle = website_session_handle
    trade = _create(user_id)
    r = client.delete(f"/v1/trades/{trade.id}", headers={"X-TL-Session-Handle": handle})
    assert r.status_code == 401
    assert _read_row(trade.id) is not None


def test_delete_removes_the_trade_its_objects_and_its_rows(
    client, website_session_handle, monkeypatch
):
    user_id, handle = website_session_handle
    trade = _create(user_id)
    from src.tradelens.api import storage as storage_module

    key = storage_module.build_object_key(user_id, trade.id, "image/png")
    _add_screenshot(trade.id, key)

    deleted_keys = []

    class _Fake:
        def delete_object(self, Bucket=None, Key=None):
            deleted_keys.append(Key)

    monkeypatch.setattr(storage_module, "_client", lambda: _Fake())

    r = _delete(client, handle, trade.id)

    assert r.status_code == 204
    assert r.content == b""
    assert deleted_keys == [key], "the R2 object must be removed, not just the row"
    assert _read_row(trade.id) is None
    assert _screenshot_rows(trade.id) == []


def test_delete_another_owners_trade_makes_no_storage_call_at_all(
    client, website_session_handle, two_users, monkeypatch
):
    """A cross-owner delete must not reach the object store even to try.

    Asserting only that the row survived would pass an implementation that
    happily deleted the other trader's images first.
    """
    user_id, handle = website_session_handle
    other = next(u for u in two_users if u != user_id)
    trade = _create(other)
    before = _read_row(trade.id)

    from src.tradelens.api.routers import trades as router_module

    spy = _CleanupSpy()
    monkeypatch.setattr(router_module.storage, "delete_trade_objects", spy)

    r = _delete(client, handle, trade.id)

    assert r.status_code == 404
    assert spy.calls == [], "no cleanup may be issued for a trade we do not own"
    assert _read_row(trade.id) == before


def test_delete_cross_owner_404_is_byte_identical_to_a_missing_trade(
    client, website_session_handle, two_users
):
    user_id, handle = website_session_handle
    other = next(u for u in two_users if u != user_id)
    theirs = _create(other)

    cross = _delete(client, handle, theirs.id)
    missing = _delete(client, handle, 999999)

    assert cross.status_code == missing.status_code == 404
    assert cross.content == missing.content


def test_delete_succeeds_when_the_object_is_already_gone(
    client, website_session_handle, monkeypatch
):
    user_id, handle = website_session_handle
    trade = _create(user_id)
    from src.tradelens.api import storage as storage_module

    key = storage_module.build_object_key(user_id, trade.id, "image/png")
    _add_screenshot(trade.id, key)

    from botocore.exceptions import ClientError

    class _Gone:
        def delete_object(self, Bucket=None, Key=None):
            raise ClientError(
                {
                    "Error": {"Code": "NoSuchKey"},
                    "ResponseMetadata": {"HTTPStatusCode": 404},
                },
                "DeleteObject",
            )

    monkeypatch.setattr(storage_module, "_client", lambda: _Gone())

    r = _delete(client, handle, trade.id)

    assert r.status_code == 204
    assert _read_row(trade.id) is None


def test_delete_reports_5xx_and_keeps_the_row_when_cleanup_fails(
    client, website_session_handle, monkeypatch
):
    """Never report a completed deletion when R2 cleanup failed.

    A trader told their screenshots are gone while private images remain in
    the bucket has been given a false privacy assurance. The row stays so the
    delete is retryable rather than an orphan nobody can find.
    """
    user_id, handle = website_session_handle
    trade = _create(user_id)
    from src.tradelens.api import storage as storage_module

    key = storage_module.build_object_key(user_id, trade.id, "image/png")
    shot_id = _add_screenshot(trade.id, key)

    from botocore.exceptions import ClientError

    class _Down:
        def delete_object(self, Bucket=None, Key=None):
            raise ClientError(
                {
                    "Error": {"Code": "InternalError"},
                    "ResponseMetadata": {"HTTPStatusCode": 500},
                },
                "DeleteObject",
            )

    monkeypatch.setattr(storage_module, "_client", lambda: _Down())

    r = _delete(client, handle, trade.id)

    assert 500 <= r.status_code < 600
    assert r.json()["detail"]["error"] == "screenshot_cleanup_failed"
    assert _read_row(trade.id) is not None, "the row must survive a failed cleanup"
    assert _screenshot_rows(trade.id) == [shot_id]


def test_delete_after_a_failed_cleanup_can_be_retried_to_completion(
    client, website_session_handle, monkeypatch
):
    user_id, handle = website_session_handle
    trade = _create(user_id)
    from src.tradelens.api import storage as storage_module

    key = storage_module.build_object_key(user_id, trade.id, "image/png")
    _add_screenshot(trade.id, key)

    from botocore.exceptions import ClientError

    class _Down:
        def delete_object(self, Bucket=None, Key=None):
            raise ClientError(
                {
                    "Error": {"Code": "InternalError"},
                    "ResponseMetadata": {"HTTPStatusCode": 500},
                },
                "DeleteObject",
            )

    deleted_keys = []

    class _Up:
        def delete_object(self, Bucket=None, Key=None):
            deleted_keys.append(Key)

    monkeypatch.setattr(storage_module, "_client", lambda: _Down())
    assert _delete(client, handle, trade.id).status_code >= 500
    assert _read_row(trade.id) is not None

    monkeypatch.setattr(storage_module, "_client", lambda: _Up())
    assert _delete(client, handle, trade.id).status_code == 204
    assert deleted_keys == [key]
    assert _read_row(trade.id) is None


def test_a_second_delete_of_a_deleted_trade_is_404(client, website_session_handle):
    user_id, handle = website_session_handle
    trade = _create(user_id)

    assert _delete(client, handle, trade.id).status_code == 204
    assert _delete(client, handle, trade.id).status_code == 404


def test_delete_cleans_objects_before_dropping_the_row(
    client, website_session_handle, monkeypatch
):
    """Ordering is load-bearing: the FK cascade drops the screenshot ROW, so
    a row deleted first would take the only record of the R2 key with it."""
    user_id, handle = website_session_handle
    trade = _create(user_id)
    from src.tradelens.api import storage as storage_module

    key = storage_module.build_object_key(user_id, trade.id, "image/png")
    _add_screenshot(trade.id, key)

    order = []

    class _Fake:
        def delete_object(self, Bucket=None, Key=None):
            order.append(("cleanup", _read_row(trade.id) is not None))

    monkeypatch.setattr(storage_module, "_client", lambda: _Fake())

    assert _delete(client, handle, trade.id).status_code == 204
    assert order == [("cleanup", True)], "objects must go while the row still exists"


def test_delete_openapi_declares_204_and_the_cleanup_failure_shape():
    spec = create_app().openapi()
    operation = spec["paths"]["/v1/trades/{trade_id}"]["delete"]
    assert "204" in operation["responses"]
    ref = operation["responses"]["503"]["content"]["application/json"]["schema"]["$ref"]
    assert ref.endswith("/ScreenshotCleanupFailedResponse")
