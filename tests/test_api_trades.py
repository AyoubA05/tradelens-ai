"""`GET /v1/trades` and `GET /v1/trades/{id}`.

Mirrors tests/test_api_overview.py: the owner comes from the session row, the
period is validated server-side even though the HMAC already covers the
query, and a second trader's rows are never reachable — a cross-owner trade
must 404, byte-identical to a genuinely missing one, never 403.
"""

from __future__ import annotations

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
