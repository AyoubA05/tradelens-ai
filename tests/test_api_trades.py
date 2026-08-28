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
from datetime import datetime, timezone

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


def test_list_ignores_every_browser_supplied_owner_alias(
    client, website_session_handle, two_users
):
    """The authenticated session row is the only authority for ownership."""
    user_id, handle = website_session_handle
    other = next(u for u in two_users if u != user_id)
    _create(other, trade_date="2026-08-10", asset="FOREIGN")
    query = (
        f"{QUERY}&user_id={other}&uid={other}&owner={other}"
        f"&accountId={other}&account_id={other}"
    )

    r = client.get(f"{LIST_PATH}?{query}", headers=_headers(handle, query=query))

    assert r.status_code == 200
    assert r.json()["total"] == 0
    assert r.json()["trades"] == []


def test_list_result_filter_matches_a_legacy_lowercase_row(
    client, website_session_handle
):
    """The historical seed script stored lowercase outcome labels."""
    user_id, handle = website_session_handle
    trade = _create(user_id, result="Win", pnl=None)
    from src.tradelens.db.models import Trade
    from src.tradelens.db.session import SessionLocal

    db = SessionLocal()
    try:
        db.query(Trade).filter(Trade.id == trade.id).update({"result": "win"})
        db.commit()
    finally:
        db.close()

    query = f"{QUERY}&result=Win"
    r = client.get(f"{LIST_PATH}?{query}", headers=_headers(handle, query=query))

    assert r.status_code == 200, r.text
    assert r.json()["total"] == 1
    assert r.json()["trades"][0]["result"] == "Win"


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


def test_list_carries_the_grade_and_screenshot_columns_the_spec_requires(
    client, website_session_handle
):
    """Spec §8: the trades table shows a grade and a screenshot indicator.

    Both lived only on TradeDetail, so the list page had to omit two required
    columns or invent them from data this endpoint does not return. A
    fabricated column on a trading journal is wrong data, not a cosmetic gap.
    """
    user_id, handle = website_session_handle
    trade = _create(user_id, trade_date="2026-08-10", ai_grade="B+", user_grade="A")
    from src.tradelens.api import storage as storage_module

    _add_screenshot(
        trade.id, storage_module.build_object_key(user_id, trade.id, "image/png")
    )
    _add_screenshot(
        trade.id, storage_module.build_object_key(user_id, trade.id, "image/png")
    )

    r = client.get(f"{LIST_PATH}?{QUERY}", headers=_headers(handle))

    assert r.status_code == 200
    row = r.json()["trades"][0]
    assert row["ai_grade"] == "B+"
    assert row["user_grade"] == "A"
    assert row["screenshot_count"] == 2


def test_list_reports_zero_screenshots_rather_than_omitting_the_field(
    client, website_session_handle
):
    """The indicator is always present, so the table renders one shape."""
    user_id, handle = website_session_handle
    _create(user_id, trade_date="2026-08-10")

    r = client.get(f"{LIST_PATH}?{QUERY}", headers=_headers(handle))

    row = r.json()["trades"][0]
    assert row["screenshot_count"] == 0
    assert row["ai_grade"] is None
    assert row["user_grade"] is None


def test_list_mints_no_presigned_urls(client, website_session_handle, monkeypatch):
    """The list shows an indicator, not images. Signing a URL per row would
    be a hundred round trips to R2 for pictures nothing on the page renders,
    and would hand out download links the trader never asked for."""
    user_id, handle = website_session_handle
    trade = _create(user_id, trade_date="2026-08-10")
    from src.tradelens.api import storage as storage_module

    _add_screenshot(
        trade.id, storage_module.build_object_key(user_id, trade.id, "image/png")
    )

    calls = []
    monkeypatch.setattr(
        storage_module,
        "presign_download",
        lambda owner, shot_id: calls.append((owner, shot_id)),
    )

    r = client.get(f"{LIST_PATH}?{QUERY}", headers=_headers(handle))

    assert r.status_code == 200
    assert r.json()["trades"][0]["screenshot_count"] == 1
    assert calls == []


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


def test_detail_normalises_a_legacy_lowercase_result_and_can_patch_it(
    client, website_session_handle
):
    """A value successfully read must not block an unrelated PATCH.

    Lowercase outcomes were emitted by the repository's seed path before
    canonical outcome writes were introduced, so this is real legacy data.
    """
    user_id, handle = website_session_handle
    trade = _create(user_id, result="Win", pnl=None, notes="old")
    from src.tradelens.db.models import Trade
    from src.tradelens.db.session import SessionLocal

    db = SessionLocal()
    try:
        db.query(Trade).filter(Trade.id == trade.id).update({"result": "win"})
        db.commit()
    finally:
        db.close()

    path = f"/v1/trades/{trade.id}"
    read = client.get(path, headers=_headers(handle, query="", path=path))
    assert read.status_code == 200, read.text
    assert read.json()["result"] == "Win"

    written = _patch(
        client,
        handle,
        trade.id,
        {
            "result": read.json()["result"],
            "notes": "edited",
            "expected_updated_at": read.json()["updated_at"],
        },
    )
    assert written.status_code == 200, written.text
    assert written.json()["notes"] == "edited"


def test_detail_maps_legacy_non_finite_numbers_to_undefined_and_can_repair_them(
    client, website_session_handle
):
    """Invalid historical numeric data must not make the whole trade unreadable.

    The strict JSON boundary represents a non-finite stored measurement as
    ``null``. The edit form can then save the record and clear the invalid
    value instead of receiving a 500 forever.
    """
    user_id, handle = website_session_handle
    trade = _create(user_id, pnl=10.0, result="Win", risk_amount=5.0)
    from src.tradelens.db.models import Trade
    from src.tradelens.db.session import SessionLocal

    db = SessionLocal()
    try:
        db.query(Trade).filter(Trade.id == trade.id).update(
            {"pnl": float("inf"), "risk_amount": float("nan")}
        )
        db.commit()
    finally:
        db.close()

    path = f"/v1/trades/{trade.id}"
    read = client.get(path, headers=_headers(handle, query="", path=path))
    assert read.status_code == 200, read.text
    assert read.json()["pnl"] is None
    assert read.json()["risk_amount"] is None

    listed = client.get(f"{LIST_PATH}?{QUERY}", headers=_headers(handle))
    assert listed.status_code == 200, listed.text
    assert listed.json()["trades"][0]["pnl"] is None

    written = _patch(
        client,
        handle,
        trade.id,
        {
            "pnl": None,
            "risk_amount": None,
            "notes": "repaired",
            "expected_updated_at": read.json()["updated_at"],
        },
    )
    assert written.status_code == 200, written.text
    assert written.json()["notes"] == "repaired"
    assert _read_row(trade.id)["pnl"] is None
    assert _read_row(trade.id)["risk_amount"] is None


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
    """The other owner's trade HAS a screenshot, deliberately.

    Built without one, `assert calls == []` was vacuous — there was nothing
    to presign, so the assertion held for any implementation and the test
    rested entirely on the 404. Attaching a real screenshot is what makes the
    spy load-bearing: a handler that shaped the response before checking
    ownership would now mint a download URL for another trader's image, and
    this fails.
    """
    user_id, handle = website_session_handle
    other = next(u for u in two_users if u != user_id)
    trade = _create(other, trade_date="2026-08-10")

    from src.tradelens.api import storage as storage_module

    _add_screenshot(
        trade.id, storage_module.build_object_key(other, trade.id, "image/png")
    )

    calls = []

    def _spy(owner, screenshot_id):
        calls.append((owner, screenshot_id))
        return "https://example.invalid/should-not-be-called"

    monkeypatch.setattr(storage_module, "presign_download", _spy)

    path = f"/v1/trades/{trade.id}"
    r = client.get(path, headers=_headers(handle, query="", path=path))
    assert r.status_code == 404
    assert calls == [], "no URL may be minted for a trade we do not own"
    assert "should-not-be-called" not in r.text


def test_detail_presigns_an_owned_screenshot_and_returns_the_typed_descriptor(
    client, website_session_handle, monkeypatch
):
    """The positive half: an owned screenshot DOES get a URL.

    Without this, the cross-owner test could be satisfied by a handler that
    never presigns anything at all. The response also has to survive
    `TradeDetail`'s `strict=True` / `extra="forbid"` — a descriptor field
    that does not typecheck would 500 rather than quietly vanish.
    """
    user_id, handle = website_session_handle
    trade = _create(user_id, trade_date="2026-08-10")

    from src.tradelens.api import storage as storage_module

    key = storage_module.build_object_key(user_id, trade.id, "image/png")
    shot_id = _add_screenshot(trade.id, key)

    calls = []

    def _spy(owner, screenshot_id):
        calls.append((owner, screenshot_id))
        return f"https://example.invalid/signed/{screenshot_id}"

    monkeypatch.setattr(storage_module, "presign_download", _spy)

    path = f"/v1/trades/{trade.id}"
    r = client.get(path, headers=_headers(handle, query="", path=path))

    assert r.status_code == 200, r.text
    assert calls == [(user_id, shot_id)], "presigned once, for this owner"
    (descriptor,) = r.json()["screenshots"]
    assert descriptor["id"] == shot_id
    assert descriptor["url"] == f"https://example.invalid/signed/{shot_id}"


def test_detail_survives_a_screenshot_that_cannot_be_presigned(
    client, website_session_handle, monkeypatch
):
    """`presign_download` returning None is a missing image, not an error —
    the rest of the trade is still owed to the trader."""
    user_id, handle = website_session_handle
    trade = _create(user_id, trade_date="2026-08-10")

    from src.tradelens.api import storage as storage_module

    key = storage_module.build_object_key(user_id, trade.id, "image/png")
    shot_id = _add_screenshot(trade.id, key)
    monkeypatch.setattr(storage_module, "presign_download", lambda *_: None)

    path = f"/v1/trades/{trade.id}"
    r = client.get(path, headers=_headers(handle, query="", path=path))

    assert r.status_code == 200, r.text
    (descriptor,) = r.json()["screenshots"]
    assert descriptor["id"] == shot_id
    assert descriptor["url"] is None


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


def _updated_at_reads(seen):
    """The SELECTs that project `trades.updated_at` and nothing else.

    That is the 404-vs-409 disambiguation re-read: after a rowcount of 0 the
    service reads the row back to decide which refusal the caller gets. The
    outcome-derivation SELECT above it projects `result, pnl`, so this
    matcher picks out exactly the statement under test.
    """
    matched = []
    for stmt, params in seen:
        # SQLAlchemy line-wraps its SQL, so collapse whitespace before
        # matching on clause boundaries.
        upper = " ".join(stmt.split()).upper()
        if not upper.startswith("SELECT") or " FROM TRADES" not in upper:
            continue
        projection = upper.split(" FROM TRADES", 1)[0]
        if "UPDATED_AT" in projection:
            matched.append((stmt, params))
    return matched


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
    assert (
        _read_row(trade.id)["trade_hash"]
        == "5f0effffb4bac6800cdbad1f313909f3c0139bbbbeb7780c72c3ecf721cb0e08"
    ), "the server-owned duplicate fingerprint must follow an edited P&L"


def test_patch_rederives_day_and_hash_when_the_trade_date_changes(
    client, website_session_handle
):
    user_id, handle = website_session_handle
    trade = _create(user_id, trade_date="2026-08-10")

    r = _patch(
        client,
        handle,
        trade.id,
        {
            "trade_date": "2026-08-11",
            "expected_updated_at": trade.updated_at,
        },
    )

    assert r.status_code == 200, r.text
    assert r.json()["day_of_week"] == "Tuesday"
    assert (
        _read_row(trade.id)["trade_hash"]
        == "96c4be1b7ba4c8e6865cbfe8251be450b232ea96082c5380afce9b3fd94836f8"
    )


def test_patch_rederives_asset_class_and_hash_when_the_asset_changes(
    client, website_session_handle
):
    user_id, handle = website_session_handle
    trade = _create(user_id, trade_date="2026-08-10", asset="NQ", asset_class="Futures")

    r = _patch(
        client,
        handle,
        trade.id,
        {"asset": "EURUSD", "expected_updated_at": trade.updated_at},
    )

    assert r.status_code == 200, r.text
    assert r.json()["asset_class"] == "Forex"
    assert (
        _read_row(trade.id)["trade_hash"]
        == "503aed4051fa12fdd34597958560af5518c1370360a65f2bdac7fb18ea8e0935"
    )


def test_full_form_round_trip_repairs_a_stale_known_asset_class(
    client, website_session_handle
):
    user_id, handle = website_session_handle
    trade = _create(user_id, asset="NQ", asset_class="Forex")

    r = _patch(
        client,
        handle,
        trade.id,
        {"asset": "NQ", "expected_updated_at": trade.updated_at},
    )

    assert r.status_code == 200, r.text
    assert r.json()["asset_class"] == "Futures"


@pytest.mark.parametrize(
    "field,value",
    [
        ("asset", None),
        ("asset", "   "),
        ("trade_date", "2026-02-30"),
        ("trade_date", "not-a-date"),
        ("followed_rules", 2),
        ("followed_rules", -1),
    ],
)
def test_patch_rejects_values_that_cannot_form_a_valid_trade(
    client, website_session_handle, field, value
):
    user_id, handle = website_session_handle
    trade = _create(user_id, asset="NQ", trade_date="2026-08-10", followed_rules=1)
    before = _read_row(trade.id)

    r = _patch(
        client,
        handle,
        trade.id,
        {field: value, "expected_updated_at": trade.updated_at},
    )

    assert r.status_code == 422, r.text
    assert _read_row(trade.id) == before


def test_patch_rejects_a_json_number_that_overflows_to_infinity(
    client, website_session_handle
):
    user_id, handle = website_session_handle
    trade = _create(user_id, pnl=10.0, result="Win")
    before = _read_row(trade.id)
    path = f"/v1/trades/{trade.id}"
    body = (
        '{"pnl":1e400,"expected_updated_at":' + json.dumps(trade.updated_at) + "}"
    ).encode()

    r = client.patch(
        path, content=body, headers=_write_headers(handle, "PATCH", path, body)
    )

    assert r.status_code == 422, r.text
    assert _read_row(trade.id) == before


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


def test_an_intervening_commit_cannot_be_lost_between_read_and_write(
    client, website_session_handle
):
    """Commit a second writer after the service read and before its UPDATE.

    A check-then-update implementation overwrites ``newer writer`` and returns
    200. The atomic timestamp predicate must return 409 and preserve it.
    """
    from sqlalchemy import event, update

    from src.tradelens.db import session as db_session
    from src.tradelens.db.models import Trade
    from src.tradelens.db.session import SessionLocal

    user_id, handle = website_session_handle
    trade = _create(user_id, notes="original")
    injected = False
    newer_stamp = "2026-08-24T12:00:00+00:00"

    def _interleave(conn, cursor, statement, parameters, context, executemany):
        nonlocal injected
        if injected or not statement.lstrip().upper().startswith("UPDATE TRADES"):
            return
        injected = True
        other = SessionLocal()
        try:
            other.execute(
                update(Trade)
                .where(Trade.id == trade.id, Trade.user_id == user_id)
                .values(notes="newer writer", updated_at=newer_stamp)
            )
            other.commit()
        finally:
            other.close()

    event.listen(db_session.engine, "before_cursor_execute", _interleave)
    try:
        r = _patch(
            client,
            handle,
            trade.id,
            {"notes": "stale writer", "expected_updated_at": trade.updated_at},
        )
    finally:
        event.remove(db_session.engine, "before_cursor_execute", _interleave)

    assert injected is True
    assert r.status_code == 409, r.text
    assert _read_row(trade.id)["notes"] == "newer writer"
    assert _read_row(trade.id)["updated_at"] == newer_stamp


def test_the_409_re_read_is_owner_scoped_too(client, website_session_handle):
    """The disambiguation re-read carries `user_id`, not just the trade id.

    Removing `Trade.user_id == owner` from that SELECT passed the entire
    suite: today the owner-scoped derivation SELECT above it returns
    `not_found` first, so the unscoped re-read is unreachable. That masking
    is precisely how a guard rots — relax or move the derivation SELECT and
    this becomes a cross-tenant existence oracle whose 409 body hands the
    caller ANOTHER OWNER'S `updated_at`. So the predicate is pinned here in
    the same way the UPDATE's predicate is pinned above, rather than left
    resting on a neighbour's behaviour.
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
    reads = _updated_at_reads(seen)
    assert len(reads) == 1, "the stale case must re-read exactly once"
    statement, params = reads[0]
    where = statement.upper().split("WHERE", 1)[1]
    for column in ("ID", "USER_ID"):
        assert column in where, f"the re-read predicate must carry {column}"
    bound = list(params.values()) if isinstance(params, dict) else list(params)
    assert trade.id in bound
    assert user_id in bound


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


def test_an_unrecognised_killzone_survives_a_full_read_modify_write(
    client, website_session_handle
):
    """What the read emits, the write must accept.

    `_killzone_label` deliberately falls back to the raw value for a killzone
    the engine does not know — legacy rows predating the killzone engine are
    still owed a fully-typed response. The write validator used to raise on
    the same value, so that trade was readable and then 422'd on save. And it
    failed the WHOLE save, including fields the trader did edit, because an
    edit form posts the entire record: a legacy row could never have its
    notes fixed. Round-tripping the exact payload the GET returned is the
    contract, so that is what this asserts.
    """
    user_id, handle = website_session_handle
    trade = _create(user_id, killzone="legacy_zone", notes="original")

    path = f"/v1/trades/{trade.id}"
    read = client.get(path, headers=_headers(handle, query="", path=path))
    assert read.status_code == 200
    body = read.json()
    assert body["killzone"] == "legacy_zone", "the read emits the raw value"

    # Post back exactly what was read, plus the one field actually edited —
    # which is what an edit form does.
    written = _patch(
        client,
        handle,
        trade.id,
        {
            "killzone": body["killzone"],
            "notes": "edited",
            "expected_updated_at": body["updated_at"],
        },
    )
    assert written.status_code == 200, written.text
    assert written.json()["killzone"] == "legacy_zone"
    assert written.json()["notes"] == "edited"

    row = _read_row(trade.id)
    assert row["killzone"] == "legacy_zone", "stored verbatim, not mangled"
    assert row["notes"] == "edited"


def test_a_known_killzone_label_still_normalises_to_its_storage_key(
    client, website_session_handle
):
    """Accepting unknown values verbatim must not weaken the known ones: a
    label the engine DOES recognise still has to be stored as its key, or
    every session filter breaks for the edited row."""
    user_id, handle = website_session_handle
    trade = _create(user_id)

    r = _patch(
        client,
        handle,
        trade.id,
        {"killzone": "New York AM", "expected_updated_at": trade.updated_at},
    )

    assert r.status_code == 200, r.text
    assert r.json()["killzone"] == "New York AM"
    assert _read_row(trade.id)["killzone"] == "ny_am"


def test_a_sample_trade_can_be_read_and_then_edited(client, website_session_handle):
    """Demo data must not be permanently un-editable.

    `load_sample_trades` built its rows without `updated_at`, and the PATCH
    guard is `updated_at = :expected_updated_at`. `NULL = x` is never true in
    SQL, so those rows listed and read fine and then refused every edit —
    with NO value a client could send: `null` failed validation and the
    empty string came back 409 carrying `current_updated_at: null`. Sample
    trades are the first thing a new trader clicks into, so this was the
    first edit anyone would ever try.
    """
    user_id, handle = website_session_handle
    from src.tradelens.services.sample_data import load_sample_trades

    assert load_sample_trades(user_id) > 0

    from src.tradelens.db.models import Trade
    from src.tradelens.db.session import SessionLocal

    db = SessionLocal()
    try:
        sample_id = (
            db.query(Trade.id)
            .filter(Trade.user_id == user_id, Trade.is_sample == 1)
            .order_by(Trade.id.asc())
            .first()[0]
        )
    finally:
        db.close()

    path = f"/v1/trades/{sample_id}"
    read = client.get(path, headers=_headers(handle, query="", path=path))
    assert read.status_code == 200
    stamp = read.json()["updated_at"]
    assert stamp is not None, "a sample trade must carry a concurrency stamp"

    written = _patch(
        client,
        handle,
        sample_id,
        {"notes": "reflected on this one", "expected_updated_at": stamp},
    )
    assert written.status_code == 200, written.text
    assert _read_row(sample_id)["notes"] == "reflected on this one"


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


def test_delete_refuses_when_a_key_was_skipped_rather_than_deleted(
    client, website_session_handle, monkeypatch
):
    """A SKIP must never earn a 204 either.

    `complete` used to be `not self.failed`, so a key the cleanup declined to
    touch still produced "your screenshots are gone". The skip path is not
    hypothetical: `_is_final_key` requires a `<uuid>.png` filename, so the
    day `finalize_upload` emits a second output format every existing key of
    that format becomes a skip — and a false privacy assurance. The
    guarantee must not depend on which list the leftover landed in.
    """
    user_id, handle = website_session_handle
    trade = _create(user_id)
    # A legacy local path: a real stored `file_path` that names no object
    # this owner is entitled to delete, so cleanup skips it.
    shot_id = _add_screenshot(trade.id, "data/screenshots/legacy-local-file.png")

    from src.tradelens.api import storage as storage_module

    touched = []

    class _Fake:
        def delete_object(self, Bucket=None, Key=None):
            touched.append(Key)

    monkeypatch.setattr(storage_module, "_client", lambda: _Fake())

    r = _delete(client, handle, trade.id)

    assert r.status_code == 503
    assert touched == [], "a skipped key must never reach the object store"
    assert _read_row(trade.id) is not None, "the row must survive"
    assert _screenshot_rows(trade.id) == [shot_id]


def test_delete_failure_body_separates_retryable_from_unresolvable(
    client, website_session_handle, monkeypatch
):
    """The caller has to tell "try again" from "this needs an operator".

    A failed key clears on retry; a skipped one never will. One opaque total
    would tell a client to keep retrying something that cannot succeed.
    """
    user_id, handle = website_session_handle
    trade = _create(user_id)
    from src.tradelens.api import storage as storage_module

    _add_screenshot(trade.id, "data/screenshots/legacy-local-file.png")

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

    key = storage_module.build_object_key(user_id, trade.id, "image/png")
    _add_screenshot(trade.id, key)
    monkeypatch.setattr(storage_module, "_client", lambda: _Down())

    r = _delete(client, handle, trade.id)

    assert r.status_code == 503
    detail = r.json()["detail"]
    assert detail["error"] == "screenshot_cleanup_failed"
    assert detail["remaining"] == 1, "the object-store fault, retryable"
    assert detail["unresolvable"] == 1, "the skipped key, which a retry cannot fix"


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


def test_patch_openapi_does_not_advertise_explicit_null_for_required_asset():
    """Omission means unchanged, but an explicit null is rejected at runtime.

    If OpenAPI says ``null`` is valid, the generated TypeScript client invites
    requests that the API deterministically rejects with 422.
    """
    asset = create_app().openapi()["components"]["schemas"]["TradeUpdate"][
        "properties"
    ]["asset"]
    assert asset["type"] == "string"
    assert "anyOf" not in asset


# ---------------------------------------------------------------- POST /v1/trades

CREATE_PATH = "/v1/trades"


def _create_headers(handle, body: bytes, *, path=CREATE_PATH, method="POST"):
    ts = str(int(time.time()))
    sig = sign_request(SECRET, ts, method, path, "", body)
    return {
        "Content-Type": "application/json",
        "X-TL-Signature": f"v1={ts}:{sig}",
        "X-TL-Session-Handle": handle,
    }


def _create_body(**overrides) -> dict:
    body = {
        "trade_date": "2026-08-10",
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


def _post(client, handle, body: dict):
    payload = json.dumps(body, separators=(",", ":")).encode()
    return client.post(
        CREATE_PATH, content=payload, headers=_create_headers(handle, payload)
    )


def test_create_unsigned_request_is_refused(client, website_session_handle):
    _, handle = website_session_handle
    body = json.dumps(_create_body(), separators=(",", ":")).encode()
    r = client.post(CREATE_PATH, content=body, headers={"X-TL-Session-Handle": handle})
    assert r.status_code == 401


def test_create_request_without_a_session_is_refused(client):
    body = json.dumps(_create_body(), separators=(",", ":")).encode()
    ts = str(int(time.time()))
    sig = sign_request(SECRET, ts, "POST", CREATE_PATH, "", body)
    r = client.post(
        CREATE_PATH, content=body, headers={"X-TL-Signature": f"v1={ts}:{sig}"}
    )
    assert r.status_code == 401


def test_create_a_tampered_body_fails_the_signature(client, website_session_handle):
    _, handle = website_session_handle
    signed = json.dumps(_create_body(), separators=(",", ":")).encode()
    tampered = json.dumps(_create_body(asset="MNQ"), separators=(",", ":")).encode()
    r = client.post(
        CREATE_PATH,
        content=tampered,
        headers=_create_headers(handle, signed),
    )
    assert r.status_code == 401


def test_create_allowlisted_fields_round_trip(client, website_session_handle):
    user_id, handle = website_session_handle
    body = _create_body(
        notes="my notes",
        emotions_before="calm",
        mistake_tags="fomo",
        setup_type="Reversal",
        session="NY AM",
        killzone="ny_am",
        htf_bias="bullish",
        followed_rules=1,
        liquidity_sweep=1,
        fvg_used=0,
    )
    r = _post(client, handle, body)
    assert r.status_code == 201, r.text
    out = r.json()
    assert out["notes"] == "my notes"
    assert out["emotions_before"] == "calm"
    assert out["mistake_tags"] == "fomo"
    assert out["setup_type"] == "Reversal"
    assert out["session"] == "NY AM"
    assert out["killzone"] == "New York AM"
    assert out["htf_bias"] == "bullish"
    assert out["followed_rules"] == 1
    assert out["liquidity_sweep"] == 1
    assert out["fvg_used"] == 0
    assert out["duplicate_of"] is None

    from src.tradelens.db.models import Trade
    from src.tradelens.db.session import SessionLocal

    db = SessionLocal()
    try:
        row = db.query(Trade).filter(Trade.id == out["id"]).first()
        assert row.user_id == user_id
    finally:
        db.close()


@pytest.mark.parametrize(
    "server_owned_field,value",
    [
        ("user_id", 999),
        ("id", 999),
        ("trade_hash", "forged"),
        ("is_sample", 1),
        ("created_at", "2020-01-01T00:00:00Z"),
        ("updated_at", "2020-01-01T00:00:00Z"),
        ("strategy_id", 1),
    ],
)
def test_create_rejects_every_server_owned_field(
    client, website_session_handle, server_owned_field, value
):
    _, handle = website_session_handle
    body = _create_body(**{server_owned_field: value})
    r = _post(client, handle, body)
    assert r.status_code == 422, r.text


def test_create_ignores_the_session_owner_never_a_body_field(
    client, website_session_handle, two_users
):
    """The owner is unreachable through the body — it comes only from the session."""
    user_id, handle = website_session_handle
    other = next(u for u in two_users if u != user_id)

    body = json.dumps(_create_body(), separators=(",", ":")).encode()
    # Sign a body containing user_id — extra="forbid" refuses it before
    # ownership would even matter, which is itself the point: there is no
    # way to get a foreign owner into this write.
    forged = json.dumps(
        {**_create_body(), "user_id": other}, separators=(",", ":")
    ).encode()
    r = client.post(
        CREATE_PATH, content=forged, headers=_create_headers(handle, forged)
    )
    assert r.status_code == 422


def test_create_second_identical_submit_creates_no_second_row(
    client, website_session_handle
):
    user_id, handle = website_session_handle
    body = _create_body()

    first = _post(client, handle, body)
    assert first.status_code == 201, first.text
    trade_id = first.json()["id"]

    from src.tradelens.db.models import Trade
    from src.tradelens.db.session import SessionLocal

    db = SessionLocal()
    try:
        count_before = db.query(Trade).count()
    finally:
        db.close()

    second = _post(client, handle, body)
    assert second.status_code == 200, second.text
    assert second.json()["duplicate_of"] == trade_id
    assert second.json()["id"] == trade_id

    db = SessionLocal()
    try:
        count_after = db.query(Trade).count()
    finally:
        db.close()
    assert count_after == count_before, "a duplicate submit must create no row"


def test_create_two_owners_submitting_identical_trades_each_get_their_own_row(
    client, website_session_handle, two_users
):
    user_id, handle = website_session_handle
    other = next(u for u in two_users if u != user_id)
    body = _create_body()

    mine = _post(client, handle, body)
    assert mine.status_code == 201, mine.text

    # The other owner submits the identical trade directly through the
    # service (no second session fixture wired here) and must get their own
    # row, not be told it is a duplicate of the first owner's.
    other_trade = trade_service.create_trade(
        {
            "trade_date": "2026-08-10",
            "asset": "NQ",
            "direction": "Long",
            "entry_price": 100.0,
            "stop_price": 95.0,
            "tp_price": 115.0,
            "result": "Win",
            "pnl": 250.0,
        },
        user_id=other,
    )
    assert other_trade.id != mine.json()["id"]

    from src.tradelens.db.models import Trade
    from src.tradelens.db.session import SessionLocal

    db = SessionLocal()
    try:
        assert db.query(Trade).filter(Trade.user_id == user_id).count() == 1
        assert db.query(Trade).filter(Trade.user_id == other).count() == 1
    finally:
        db.close()


def test_create_future_trade_date_is_422(client, website_session_handle):
    _, handle = website_session_handle
    r = _post(client, handle, _create_body(trade_date="2099-01-01"))
    assert r.status_code == 422


# ---------------------------------------------------- POST /v1/trades: owner calendar
#
# The create route's future-date ceiling is `today_for_owner`, the same
# owner-calendar resolution Phase 3E established for Overview's Today/This
# Week. A UTC-only ceiling refuses a trader's genuine "today" for hours
# around UTC midnight whenever they are ahead of UTC.
#
# `today_for_owner(owner)` takes no `now_utc` override from the route (only
# `services/overview.py`'s tests get to inject one directly), so determinism
# here comes from pinning the wall clock `today_for_owner` reads —
# `app_settings.datetime.now(timezone.utc)` — to one fixed instant, the same
# way `freezegun` or any clock-injection tool would. That pins *when "now"
# is*, not *how the owner's date is computed from it*: the zone conversion,
# the persisted-timezone lookup, and the fallback chain in `today_for_owner`
# all still run for real. Patching `today_for_owner` itself (or the route's
# imported reference to it) would instead stub out the exact resolution
# under test, so that is deliberately not what happens here.
_FIXED_UTC_INSTANT = datetime(2026, 8, 20, 23, 30, tzinfo=timezone.utc)


class _FixedClockDatetime(datetime):
    """A `datetime` subclass whose `.now()` always returns the pinned instant.

    Only `.now()` is overridden; every other classmethod/constructor path
    (`.replace`, `.astimezone`, arithmetic) is inherited unchanged, so
    `today_for_owner`'s zone conversion runs on real `datetime` machinery
    against a frozen starting instant rather than a mocked result.
    """

    @classmethod
    def now(cls, tz=None):
        return _FIXED_UTC_INSTANT.astimezone(tz) if tz else _FIXED_UTC_INSTANT


@pytest.fixture
def frozen_clock(monkeypatch):
    """Pin every clock this test could exercise to `_FIXED_UTC_INSTANT`.

    `today_for_owner` reads `datetime.now(timezone.utc)` through the module
    global `app_settings.datetime`; `trades.py` imports the *function*
    `today_for_owner`, not the module, so its calls still execute inside
    `app_settings`'s namespace and see that patch.

    `trades.py` ALSO imports its own `datetime` name (for the fingerprint/
    idempotency-window logic elsewhere in the router), and that name is what
    the pre-fix ceiling — `datetime.now(timezone.utc).strftime(...)` — reads
    directly rather than through `today_for_owner`. Freezing only
    `app_settings.datetime` left the mutation-testing check below
    non-deterministic: reverting the route to the old UTC-only line ignored
    this fixture entirely and fell back to the real wall clock, so the
    headline test only happened to catch the regression when run before
    2026-08-21 in real time — exactly the kind of flakiness this task warns
    against. Freezing both names makes the fix under test, and the bug it
    replaced, read the same pinned instant either way.
    """
    from src.tradelens.api.routers import trades as trades_module
    from src.tradelens.services import app_settings

    monkeypatch.setattr(app_settings, "datetime", _FixedClockDatetime)
    monkeypatch.setattr(trades_module, "datetime", _FixedClockDatetime)


def test_create_todays_date_in_a_zone_ahead_of_utc_is_accepted(
    client, website_session_handle, frozen_clock
):
    """The headline case: Kiritimati (UTC+14) is already tomorrow when UTC is not.

    At the frozen instant, 2026-08-20 23:30 UTC, UTC's calendar date is still
    the 20th, but Kiritimati (the zone Phase 3E used to prove this exact
    class of fix) is already 2026-08-21 13:30 local. `trade_date` "2026-08-21"
    is this owner's real today and must be accepted. Against the old
    UTC-only ceiling it is tomorrow and gets refused — see the mutation
    check in this file's companion report.

    The timezone is set through `app_settings.set_timezone`, the app's own
    mechanism, not by patching resolution internals — the only thing patched
    is the wall clock (`frozen_clock`), never the owner-date computation
    itself.
    """
    from src.tradelens.services import app_settings

    user_id, handle = website_session_handle
    app_settings.set_timezone(user_id, "Pacific/Kiritimati")

    r = _post(client, handle, _create_body(trade_date="2026-08-21"))

    assert r.status_code == 201, r.text
    assert r.json()["trade_date"] == "2026-08-21"


def test_create_tomorrow_in_the_owner_s_own_zone_is_still_422(
    client, website_session_handle, frozen_clock
):
    """A genuinely future date is still refused once resolved through the owner's zone."""
    from src.tradelens.services import app_settings

    user_id, handle = website_session_handle
    app_settings.set_timezone(user_id, "Pacific/Kiritimati")

    # At the frozen instant, Kiritimati's own today is 2026-08-21 (see the
    # headline test above); 08-22 is tomorrow in that same zone.
    r = _post(client, handle, _create_body(trade_date="2026-08-22"))

    assert r.status_code == 422


def test_create_with_no_saved_timezone_falls_back_and_still_creates(
    client, website_session_handle
):
    """An owner who never set a timezone gets the product default, not an error."""
    _, handle = website_session_handle
    r = _post(client, handle, _create_body(trade_date="2026-08-10"))
    assert r.status_code == 201, r.text


def test_create_with_an_invalid_saved_timezone_falls_back_and_still_creates(
    client, website_session_handle
):
    """A corrupted/invalid saved zone must resolve via fallback, never raise."""
    from src.tradelens.services import app_settings

    user_id, handle = website_session_handle
    app_settings.set_timezone(user_id, "Not/AZone")

    r = _post(client, handle, _create_body(trade_date="2026-08-10"))

    assert r.status_code == 201, r.text


def test_create_outcome_contradicting_pnl_is_422_not_500(
    client, website_session_handle
):
    _, handle = website_session_handle
    r = _post(client, handle, _create_body(result="Win", pnl=-500.0))
    assert r.status_code == 422
    assert r.status_code != 500


def test_create_response_is_not_cacheable(client, website_session_handle):
    _, handle = website_session_handle
    r = _post(client, handle, _create_body())
    assert "no-store" in r.headers.get("cache-control", "")


def test_create_openapi_contract_covers_every_trade_column():
    """Every `Trade` column is deliberately in exactly one of the create sets.

    A column added to the model later belongs to neither
    `CREATABLE_TRADE_FIELDS` nor `SERVER_OWNED_ON_CREATE` until someone files
    it — this test fails until they do, so the write surface cannot silently
    widen.
    """
    from src.tradelens.api.schemas.trades import (
        CREATABLE_TRADE_FIELDS,
        SERVER_OWNED_ON_CREATE,
    )
    from src.tradelens.db.models import Trade

    model_columns = {c.key for c in Trade.__table__.columns}
    accounted = CREATABLE_TRADE_FIELDS | SERVER_OWNED_ON_CREATE
    assert model_columns == accounted, model_columns.symmetric_difference(accounted)
    assert CREATABLE_TRADE_FIELDS.isdisjoint(SERVER_OWNED_ON_CREATE)


# ------------------------------------- POST /v1/trades/{id}/screenshot/presign


class _FakeS3:
    """Records what was asked of R2 so a test can assert that NOTHING was."""

    def __init__(self, objects=None):
        self.objects = objects or {}
        self.signed = []
        self.puts = {}
        self.deleted = []
        self.gets = []

    def generate_presigned_url(self, operation, Params=None, ExpiresIn=None):
        self.signed.append((operation, Params))
        return f"https://r2.example/{Params['Key']}?sig=x"

    def get_object(self, Bucket=None, Key=None):
        self.gets.append(Key)
        data = self.objects[Key]
        return {"ContentLength": len(data), "Body": _Body(data)}

    def put_object(self, Bucket=None, Key=None, **kwargs):
        self.puts[Key] = kwargs

    def delete_object(self, Bucket=None, Key=None):
        self.deleted.append(Key)


class _Body:
    def __init__(self, data):
        self.data = data

    def read(self, amount=None):
        return self.data if amount is None else self.data[:amount]

    def close(self):
        return None


def _presign_path(trade_id):
    return f"/v1/trades/{trade_id}/screenshot/presign"


def _post_signed(client, handle, path, body):
    payload = json.dumps(body, separators=(",", ":")).encode()
    return client.post(
        path, content=payload, headers=_create_headers(handle, payload, path=path)
    )


@pytest.fixture
def fake_r2(monkeypatch):
    from src.tradelens.api import storage

    fake = _FakeS3()
    monkeypatch.setattr(storage, "_client", lambda: fake)
    return fake


def test_presign_returns_a_url_under_the_callers_quarantine_prefix(
    client, website_session_handle, fake_r2
):
    user_id, handle = website_session_handle
    trade = _create(user_id)

    r = _post_signed(
        client, handle, _presign_path(trade.id), {"content_type": "image/png"}
    )

    assert r.status_code == 200
    body = r.json()
    assert body["key"].startswith(f"quarantine/u/{user_id}/t/{trade.id}/")
    assert body["url"].startswith("https://r2.example/")
    assert body["expires_in"] > 0
    assert body["max_bytes"] > 0


def test_presign_on_another_owners_trade_is_404_and_signs_nothing(
    client, website_session_handle, two_users, fake_r2
):
    """Ownership is what refuses this. The trade exists and the request is
    perfectly well-formed — only the owner differs, so a 403 would confirm the
    row exists and a signed URL would hand over an upload slot in someone
    else's namespace."""
    user_id, handle = website_session_handle
    other = next(u for u in two_users if u != user_id)
    theirs = _create(other)

    r = _post_signed(
        client, handle, _presign_path(theirs.id), {"content_type": "image/png"}
    )

    assert r.status_code == 404
    assert r.json() == {"detail": "trade not found"}
    assert fake_r2.signed == [], "a refused request must sign nothing at all"


def test_presign_for_a_missing_trade_is_byte_identical_to_a_foreign_one(
    client, website_session_handle, two_users, fake_r2
):
    user_id, handle = website_session_handle
    other = next(u for u in two_users if u != user_id)
    theirs = _create(other)

    foreign = _post_signed(
        client, handle, _presign_path(theirs.id), {"content_type": "image/png"}
    )
    missing = _post_signed(
        client, handle, _presign_path(999_999), {"content_type": "image/png"}
    )

    assert foreign.status_code == missing.status_code == 404
    assert foreign.content == missing.content


@pytest.mark.parametrize(
    "content_type", ["image/svg+xml", "text/html", "application/pdf", ""]
)
def test_presign_refuses_an_unsupported_content_type_before_signing(
    client, website_session_handle, fake_r2, content_type
):
    """SVG is script-bearing markup, not a picture. The refusal happens in the
    request contract, so nothing is signed and no upload slot exists."""
    user_id, handle = website_session_handle
    trade = _create(user_id)

    r = _post_signed(
        client, handle, _presign_path(trade.id), {"content_type": content_type}
    )

    assert r.status_code == 422
    assert fake_r2.signed == []


def test_presign_rejects_a_client_supplied_key(client, website_session_handle, fake_r2):
    """The server chooses where bytes land, always."""
    user_id, handle = website_session_handle
    trade = _create(user_id)

    r = _post_signed(
        client,
        handle,
        _presign_path(trade.id),
        {"content_type": "image/png", "key": "u/1/t/1/anything.png"},
    )

    assert r.status_code == 422
    assert fake_r2.signed == []


def test_the_presign_contract_covers_exactly_the_storage_allowlist():
    """A Literal cannot be derived from a dict, so this is what keeps the
    request contract and `storage.ALLOWED_CONTENT_TYPES` from drifting."""
    from typing import get_args

    from src.tradelens.api import storage
    from src.tradelens.api.schemas.trades import ScreenshotContentType

    assert set(get_args(ScreenshotContentType)) == set(storage.ALLOWED_CONTENT_TYPES)


# ------------------------------------ POST /v1/trades/{id}/screenshot/finalize


def _finalize_path(trade_id):
    return f"/v1/trades/{trade_id}/screenshot/finalize"


def _png_bytes(size=(3, 2)):
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGB", size, "teal").save(buf, format="PNG")
    return buf.getvalue()


def _quarantine_key(user_id, trade_id, name="uploaded"):
    return f"quarantine/u/{user_id}/t/{trade_id}/{name}.png"


def _screenshot_rows(trade_id):
    from src.tradelens.db.models import Screenshot
    from src.tradelens.db.session import SessionLocal

    db = SessionLocal()
    try:
        return db.query(Screenshot).filter(Screenshot.trade_id == trade_id).all()
    finally:
        db.close()


def test_finalize_records_a_row_under_the_owners_final_prefix(
    client, website_session_handle, monkeypatch
):
    from src.tradelens.api import storage

    user_id, handle = website_session_handle
    trade = _create(user_id)
    key = _quarantine_key(user_id, trade.id)
    fake = _FakeS3(objects={key: _png_bytes()})
    monkeypatch.setattr(storage, "_client", lambda: fake)

    r = _post_signed(client, handle, _finalize_path(trade.id), {"key": key})

    assert r.status_code == 201
    body = r.json()
    assert body["width"] == 3 and body["height"] == 2
    assert body["uploaded_at"], "the client shows when a screenshot was attached"

    rows = _screenshot_rows(trade.id)
    assert len(rows) == 1
    assert rows[0].id == body["id"]
    assert rows[0].file_path.startswith(f"u/{user_id}/t/{trade.id}/")
    assert rows[0].file_path.endswith(".png")
    # The quarantine object is gone: nothing untrusted is left in the bucket.
    assert key in fake.deleted


def test_finalize_promotes_re_encoded_bytes_not_the_uploaded_ones(
    client, website_session_handle, monkeypatch
):
    """The bytes a viewer downloads are never the bytes that were uploaded.

    A polyglot — a valid PNG with an appended payload — survives every header
    check ever written and does not survive being decoded and written out
    fresh. Asserting the promoted body DIFFERS from the upload is what proves
    a re-encode happened rather than a copy.
    """
    from src.tradelens.api import storage

    user_id, handle = website_session_handle
    trade = _create(user_id)
    key = _quarantine_key(user_id, trade.id)
    uploaded = _png_bytes() + b"<script>payload</script>"
    fake = _FakeS3(objects={key: uploaded})
    monkeypatch.setattr(storage, "_client", lambda: fake)

    r = _post_signed(client, handle, _finalize_path(trade.id), {"key": key})

    assert r.status_code == 201
    promoted_key = _screenshot_rows(trade.id)[0].file_path
    promoted = fake.puts[promoted_key]["Body"]
    assert promoted != uploaded
    assert b"<script>" not in promoted
    assert fake.puts[promoted_key]["ContentType"] == "image/png"


def test_finalize_refuses_a_key_naming_another_owners_quarantine(
    client, website_session_handle, two_users, monkeypatch
):
    """Ownership — not malformed input — is what refuses this.

    The trade IS the caller's, so `_owns_trade` passes. The key is perfectly
    well-formed and the object exists in the fake bucket, so no downstream
    gate (decode, size, extension) would reject it either. The ONLY thing that
    can refuse it is `finalize_upload` re-deriving the caller's own quarantine
    prefix and finding the key names user `other`'s. Remove that
    re-derivation and this test promotes another tenant's bytes into the
    caller's trade.
    """
    from src.tradelens.api import storage

    user_id, handle = website_session_handle
    other = next(u for u in two_users if u != user_id)
    mine = _create(user_id)
    forged = _quarantine_key(other, mine.id, "theirs")
    fake = _FakeS3(objects={forged: _png_bytes()})
    monkeypatch.setattr(storage, "_client", lambda: fake)

    r = _post_signed(client, handle, _finalize_path(mine.id), {"key": forged})

    assert r.status_code == 404
    assert r.json() == {"detail": "trade not found"}
    assert fake.gets == [], "a refused key must never be read from the bucket"
    assert fake.puts == {}
    assert _screenshot_rows(mine.id) == []


def test_finalize_on_another_owners_trade_is_404(
    client, website_session_handle, two_users, monkeypatch
):
    from src.tradelens.api import storage

    user_id, handle = website_session_handle
    other = next(u for u in two_users if u != user_id)
    theirs = _create(other)
    key = _quarantine_key(other, theirs.id)
    fake = _FakeS3(objects={key: _png_bytes()})
    monkeypatch.setattr(storage, "_client", lambda: fake)

    r = _post_signed(client, handle, _finalize_path(theirs.id), {"key": key})

    assert r.status_code == 404
    assert fake.gets == []
    assert _screenshot_rows(theirs.id) == []


def test_finalize_refuses_a_non_image(client, website_session_handle, monkeypatch):
    from src.tradelens.api import storage

    user_id, handle = website_session_handle
    trade = _create(user_id)
    key = _quarantine_key(user_id, trade.id)
    fake = _FakeS3(objects={key: b"<html><script>not a picture</script></html>"})
    monkeypatch.setattr(storage, "_client", lambda: fake)

    r = _post_signed(client, handle, _finalize_path(trade.id), {"key": key})

    assert r.status_code == 422
    assert fake.puts == {}, "nothing untrusted may be promoted"
    assert key in fake.deleted, "a rejected upload is discarded, not left behind"
    assert _screenshot_rows(trade.id) == []


def test_finalize_refuses_an_oversized_upload(
    client, website_session_handle, monkeypatch
):
    from src.tradelens.api import storage

    user_id, handle = website_session_handle
    trade = _create(user_id)
    key = _quarantine_key(user_id, trade.id)
    fake = _FakeS3(objects={key: b"x" * (storage.MAX_UPLOAD_BYTES + 1)})
    monkeypatch.setattr(storage, "_client", lambda: fake)

    r = _post_signed(client, handle, _finalize_path(trade.id), {"key": key})

    assert r.status_code == 422
    assert fake.puts == {}
    assert _screenshot_rows(trade.id) == []


def test_finalize_refuses_a_decompression_bomb(
    client, website_session_handle, monkeypatch
):
    """A small file that expands into gigabytes of pixels. Refused on its
    declared dimensions, before Pillow is asked to allocate them."""
    import io

    from PIL import Image

    from src.tradelens.api import storage
    from src.tradelens.api import imaging

    user_id, handle = website_session_handle
    trade = _create(user_id)
    key = _quarantine_key(user_id, trade.id)
    bomb = io.BytesIO()
    huge = imaging.MAX_DIMENSION + 1
    Image.new("L", (huge, 1)).save(bomb, format="PNG")
    fake = _FakeS3(objects={key: bomb.getvalue()})
    monkeypatch.setattr(storage, "_client", lambda: fake)

    r = _post_signed(client, handle, _finalize_path(trade.id), {"key": key})

    assert r.status_code == 422
    assert fake.puts == {}
    assert _screenshot_rows(trade.id) == []


def test_finalize_deletes_the_promoted_object_when_the_row_write_fails(
    client, website_session_handle, monkeypatch
):
    """A promoted object with no screenshots row is unreachable AND unsweepable.

    `delete_trade_objects` resolves keys FROM `screenshots.file_path`, so an
    unrecorded final object is an orphan nothing can find or remove — strictly
    worse than a quarantine orphan, which at least has no download path. The
    promote must be undone before the error is surfaced.
    """
    from src.tradelens.api import storage
    from src.tradelens.services import screenshot_service

    user_id, handle = website_session_handle
    trade = _create(user_id)
    key = _quarantine_key(user_id, trade.id)
    fake = _FakeS3(objects={key: _png_bytes()})
    monkeypatch.setattr(storage, "_client", lambda: fake)

    def _boom(*args, **kwargs):
        raise RuntimeError("database is unavailable")

    monkeypatch.setattr(screenshot_service, "record_object_screenshot", _boom)

    r = _post_signed(client, handle, _finalize_path(trade.id), {"key": key})

    assert r.status_code == 503
    assert _screenshot_rows(trade.id) == []
    promoted = list(fake.puts)
    assert len(promoted) == 1
    assert promoted[0] in fake.deleted, (
        "the promoted object must be removed before the error is surfaced, "
        "or it is an orphan nothing can find"
    )


def test_finalize_rejects_a_body_carrying_anything_but_a_key(
    client, website_session_handle, monkeypatch
):
    from src.tradelens.api import storage

    user_id, handle = website_session_handle
    trade = _create(user_id)
    fake = _FakeS3()
    monkeypatch.setattr(storage, "_client", lambda: fake)

    r = _post_signed(
        client,
        handle,
        _finalize_path(trade.id),
        {"key": _quarantine_key(user_id, trade.id), "width": 9999},
    )

    assert r.status_code == 422
    assert fake.gets == []
