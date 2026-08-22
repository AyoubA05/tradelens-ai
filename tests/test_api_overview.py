# tests/test_api_overview.py
"""The Overview endpoint.

The security properties are the point: the owner comes from the session row,
the period is validated server-side even though the HMAC already covers it,
and a second trader's data is unreachable.
"""
import time

import pytest
from fastapi.testclient import TestClient

from src.tradelens.api.app import create_app
from src.tradelens.api.security import sign_request
from tests.parity.dataset import seed_golden_dataset

SECRET = "test-service-secret-value-at-least-32-bytes"
PATH = "/v1/overview"
QUERY = "from=2026-08-01&to=2026-08-31"


@pytest.fixture
def client(monkeypatch):
    # Mirrors tests/test_api_security.py's `client` fixture: `validate_api_runtime`
    # requires a >=32 byte secret and a postgres-looking DATABASE_URL at app
    # creation time. The `two_users` fixture (pulled in transitively via
    # `website_session_handle`) later overwrites DATABASE_URL to the isolated
    # sqlite tmp path and patches `settings.database_url` directly — that is
    # what the service layer actually reads, so this fake postgres URL only
    # needs to satisfy the one-time production-config check, never a real query.
    monkeypatch.setenv("TL_SERVICE_SECRET", SECRET)
    monkeypatch.delenv("TL_SERVICE_SECRET_PREVIOUS", raising=False)
    monkeypatch.setenv("TL_ENV", "production")
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://user:password@example.invalid/tradelens?sslmode=require",
    )
    return TestClient(create_app(), raise_server_exceptions=False)


def _headers(handle, *, query=QUERY, path=PATH):
    ts = str(int(time.time()))
    sig = sign_request(SECRET, ts, "GET", path, query, b"")
    return {"X-TL-Signature": f"v1={ts}:{sig}", "X-TL-Session-Handle": handle}


def test_unsigned_request_is_refused(client, website_session_handle):
    _, handle = website_session_handle
    assert (
        client.get(
            f"{PATH}?{QUERY}", headers={"X-TL-Session-Handle": handle}
        ).status_code
        == 401
    )


def test_request_without_a_session_is_refused(client):
    ts = str(int(time.time()))
    sig = sign_request(SECRET, ts, "GET", PATH, QUERY, b"")
    r = client.get(f"{PATH}?{QUERY}", headers={"X-TL-Signature": f"v1={ts}:{sig}"})
    assert r.status_code == 401


def test_returns_the_owner_s_overview(client, website_session_handle):
    user_id, handle = website_session_handle
    seed_golden_dataset(user_id)
    r = client.get(f"{PATH}?{QUERY}", headers=_headers(handle))
    assert r.status_code == 200
    body = r.json()
    assert body["kpi"]["net_pnl"] == 575.0
    assert body["kpi"]["trades"] == 5


def test_never_returns_another_owner_s_data(client, website_session_handle, two_users):
    """A signed, authenticated request still only sees its own rows."""
    user_id, handle = website_session_handle
    other = [u for u in two_users if u != user_id][0]
    seed_golden_dataset(other)
    body = client.get(f"{PATH}?{QUERY}", headers=_headers(handle)).json()
    assert body["kpi"]["trades"] == 0


def test_a_tampered_period_fails_the_signature(client, website_session_handle):
    """The query is bound into the HMAC, so the range cannot be edited in transit."""
    _, handle = website_session_handle
    r = client.get(f"{PATH}?from=1990-01-01&to=2099-01-01", headers=_headers(handle))
    assert r.status_code == 401


def test_a_nonsense_period_is_rejected_with_422(client, website_session_handle):
    """Authenticated is not the same as valid."""
    _, handle = website_session_handle
    bad = "from=not-a-date&to=2026-08-31"
    r = client.get(f"{PATH}?{bad}", headers=_headers(handle, query=bad))
    assert r.status_code == 422


def test_a_reversed_period_is_rejected(client, website_session_handle):
    _, handle = website_session_handle
    bad = "from=2026-08-31&to=2026-08-01"
    r = client.get(f"{PATH}?{bad}", headers=_headers(handle, query=bad))
    assert r.status_code == 422


def test_the_response_is_not_cacheable(client, website_session_handle):
    _, handle = website_session_handle
    r = client.get(f"{PATH}?{QUERY}", headers=_headers(handle))
    assert "no-store" in r.headers.get("cache-control", "")


def test_the_schema_is_typed_not_a_bare_dict(client, website_session_handle):
    """A dict response generates {[k:string]: unknown} and the drift gate then
    protects nothing.

    `get_type_hints` rather than the raw `__annotations__` dict: the router
    module carries `from __future__ import annotations` (the Python 3.9 floor
    this repo targets), which stores every annotation as an unevaluated
    string — `__annotations__["return"]` would be the literal string
    "OverviewResponse", not the class, and `.__name__` would fail on it either
    way.
    """
    from typing import get_type_hints

    from src.tradelens.api.routers.overview import get_overview

    assert get_type_hints(get_overview)["return"].__name__ == "OverviewResponse"
