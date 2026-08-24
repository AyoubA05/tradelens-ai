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
