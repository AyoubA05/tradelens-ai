"""Both locks, and the hardening that keeps this service non-browser-facing.

Neither lock is sufficient alone: Lock 1 (the HMAC signature) proves the caller
is our own frontend and says nothing about identity; Lock 2 (the session token,
resolved against the database) establishes identity. Requests carrying only one
must be refused, and both of those cases are asserted below.
"""
import time

import pytest
from fastapi.testclient import TestClient

from src.tradelens.api.app import create_app
from src.tradelens.api.security import sign_request

SECRET = "test-service-secret-value"
PATH = "/v1/session/whoami"


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("TL_SERVICE_SECRET", SECRET)
    monkeypatch.delenv("TL_SERVICE_SECRET_PREVIOUS", raising=False)
    monkeypatch.setenv("TL_ENV", "production")
    return TestClient(create_app(), raise_server_exceptions=False)


def _headers(session_token, *, method="GET", path=PATH, query="", body=b"",
             secret=SECRET, timestamp=None):
    ts = timestamp or str(int(time.time()))
    sig = sign_request(secret, ts, method, path, query, body)
    return {
        "X-TL-Signature": f"v1={ts}:{sig}",
        "X-TL-Session": session_token,
    }


def test_health_needs_no_credentials(client):
    assert client.get("/health").status_code == 200


def test_a_request_with_no_signature_is_refused(client, website_session):
    """Lock 2 alone is not enough."""
    r = client.get(PATH, headers={"X-TL-Session": website_session[1]})
    assert r.status_code == 401


def test_a_valid_signature_with_no_session_is_refused(client):
    """Lock 1 alone is not enough. The service secret proves the caller is our
    frontend; it says nothing about which user is asking."""
    ts = str(int(time.time()))
    sig = sign_request(SECRET, ts, "GET", PATH, "", b"")
    r = client.get(PATH, headers={"X-TL-Signature": f"v1={ts}:{sig}"})
    assert r.status_code == 401


def test_both_locks_together_succeed(client, website_session):
    user_id, token = website_session
    r = client.get(PATH, headers=_headers(token))
    assert r.status_code == 200
    assert r.json() == {"user_id": user_id}


def test_a_signature_from_the_wrong_secret_is_refused(client, website_session):
    _, token = website_session
    r = client.get(PATH, headers=_headers(token, secret="wrong-secret"))
    assert r.status_code == 401


def test_an_old_signature_is_refused(client, website_session):
    """The replay window. A captured header must stop working quickly."""
    _, token = website_session
    old = str(int(time.time()) - 3600)
    r = client.get(PATH, headers=_headers(token, timestamp=old))
    assert r.status_code == 401


def test_a_signature_for_a_different_path_is_refused(client, website_session):
    """The path is bound into the signature, so a header captured from one
    endpoint cannot be replayed against another."""
    _, token = website_session
    ts = str(int(time.time()))
    sig = sign_request(SECRET, ts, "GET", "/health", "", b"")
    r = client.get(PATH, headers={"X-TL-Signature": f"v1={ts}:{sig}",
                                 "X-TL-Session": token})
    assert r.status_code == 401


def test_a_revoked_session_is_refused(client, website_session):
    from src.tradelens.services import auth_sessions

    user_id, token = website_session
    auth_sessions.revoke_all_for_user(user_id)
    assert client.get(PATH, headers=_headers(token)).status_code == 401


def test_a_garbage_session_token_is_refused(client, website_session):
    _, _token = website_session
    assert client.get(PATH, headers=_headers("not-a-real-token")).status_code == 401


def test_the_user_id_comes_from_the_session_not_the_request(client, website_session):
    """The single most important property: a caller cannot name the account it
    wants to act on. The query string is not part of the signed path, so this
    request is otherwise perfectly valid."""
    user_id, token = website_session
    r = client.get(
        f"{PATH}?user_id=999999",
        headers=_headers(token, query="user_id=999999"),
    )
    assert r.status_code == 200
    assert r.json()["user_id"] == user_id


def test_no_cors_headers_are_ever_emitted(client, website_session):
    """This service is not browser-consumed. A CORS header would be the first
    step toward it becoming so."""
    _, token = website_session
    r = client.get(PATH, headers=_headers(token))
    assert not any(h.lower().startswith("access-control-") for h in r.headers)


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
def test_the_schema_is_not_served_in_production(client, path):
    assert client.get(path).status_code == 404


def test_authenticated_responses_are_not_cacheable(client, website_session):
    _, token = website_session
    r = client.get(PATH, headers=_headers(token))
    assert "no-store" in r.headers.get("cache-control", "")


def test_a_rotated_previous_secret_is_still_accepted(client, website_session,
                                                     monkeypatch):
    """Rotation must not require both sides to change in the same instant."""
    monkeypatch.setenv("TL_SERVICE_SECRET", "the-new-secret")
    monkeypatch.setenv("TL_SERVICE_SECRET_PREVIOUS", SECRET)
    _, token = website_session
    assert client.get(PATH, headers=_headers(token, secret=SECRET)).status_code == 200


def test_no_api_module_imports_a_maintenance_helper():
    """Global-access helpers must never be reachable from a request path.
    None exists today; this fails the moment one is imported here."""
    import pathlib
    import re

    offenders = []
    for path in pathlib.Path("src/tradelens/api").rglob("*.py"):
        if re.search(r"\b\w*(_for_maintenance|_all_users)\b", path.read_text()):
            offenders.append(str(path))
    assert offenders == []


# --- query binding -------------------------------------------------------
#
# The query string is part of the signed message. Before it was, a handler
# reading a filter or a cursor from the query string would have been consuming
# an input Lock 1 never covered.


def test_an_unsigned_query_parameter_is_refused(client, website_session):
    """Appending a parameter to a request signed without one must not verify.

    This is the finding these tests exist for: the signature must cover the
    query, not merely the path it hangs off.
    """
    _, token = website_session
    r = client.get(f"{PATH}?user_id=999999", headers=_headers(token, query=""))
    assert r.status_code == 401


def test_a_tampered_query_value_is_refused(client, website_session):
    """A signature issued for one value must not carry another."""
    _, token = website_session
    r = client.get(
        f"{PATH}?limit=999",
        headers=_headers(token, query="limit=10"),
    )
    assert r.status_code == 401


def test_a_dropped_query_parameter_is_refused(client, website_session):
    """Removal is tampering too — a signed filter must not be strippable."""
    _, token = website_session
    r = client.get(PATH, headers=_headers(token, query="limit=10"))
    assert r.status_code == 401


def test_reordered_query_parameters_still_verify(client, website_session):
    """Canonicalisation earns its keep here.

    `?a=1&b=2` and `?b=2&a=1` are the same request by every semantic that
    matters, so a layer that reorders parameters between signer and verifier
    must not break authentication.
    """
    user_id, token = website_session
    r = client.get(
        f"{PATH}?b=2&a=1",
        headers=_headers(token, query="a=1&b=2"),
    )
    assert r.status_code == 200
    assert r.json()["user_id"] == user_id


def test_a_signed_query_is_accepted(client, website_session):
    user_id, token = website_session
    r = client.get(
        f"{PATH}?limit=10&offset=5",
        headers=_headers(token, query="limit=10&offset=5"),
    )
    assert r.status_code == 200
    assert r.json()["user_id"] == user_id


def test_an_old_signature_on_a_query_request_is_refused(client, website_session):
    """Replay: binding the query must not weaken the freshness bound."""
    _, token = website_session
    old = str(int(time.time()) - 3600)
    r = client.get(
        f"{PATH}?limit=10",
        headers=_headers(token, query="limit=10", timestamp=old),
    )
    assert r.status_code == 401
