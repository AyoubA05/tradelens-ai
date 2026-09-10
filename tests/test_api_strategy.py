"""`/v1/strategy` — the playbook API.

The profile is AI input, so these tests care about who can write it, whether
a stale tab can overwrite it, and whether anything a browser sends can pick a
column, an owner, or the text of a rule.

Isolation tests authenticate the SECOND user. `website_session_handle` is
always user 1, which makes it blind to an endpoint that hardcodes `user_id=1`.
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
from src.tradelens.api.schemas.strategy import StrategyResponse
from src.tradelens.api.security import sign_request
from src.tradelens.db.models import AIAnalysis, Trade
from src.tradelens.db.session import SessionLocal
from src.tradelens.services import corrections, strategy
from src.tradelens.services import strategy_writes as sw
from src.tradelens.services.strategy_playbook import (
    STARTER_TEMPLATE,
    profile_completion,
)
from src.tradelens.services.users import get_onboarding_state

SECRET = "test-service-secret-value-at-least-32-bytes"
FIELDS = sorted(strategy._PROFILE_FIELDS)
BLANK = {f: None for f in FIELDS}
RULE = "• bias: prefer bearish (from repeated corrections in review)"


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
    """A live website session handle for an ARBITRARY user (see module doc)."""
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
        sig = sign_request(SECRET, ts, method, path, "", body)
        headers["X-TL-Signature"] = "v1={}:{}".format(ts, sig)
    if handle is not None:
        headers["X-TL-Session-Handle"] = handle
    return client.request(method, path, content=body, headers=headers)


def _put(client, handle, fields, revision):
    return _call(
        client,
        handle,
        "PUT",
        "/v1/strategy",
        dict(fields, expected_revision=revision),
    )


def _repeat(owner, field="bias", value="bearish", n=5):
    for _ in range(n):
        db = SessionLocal()
        try:
            trade = Trade(user_id=owner, asset="NQ", direction="Long", result="Win")
            db.add(trade)
            db.flush()
            analysis = AIAnalysis(trade_id=trade.id, bias="bullish", trade_quality=7)
            db.add(analysis)
            db.commit()
            trade_id, analysis_id = trade.id, analysis.id
        finally:
            db.close()
        corrections.record_correction(
            trade_id, analysis_id, field, "bullish", value, user_id=owner
        )


# ── Isolation ─────────────────────────────────────────────────────────────


def test_get_returns_the_second_users_profile_not_the_first(client, two_users):
    first, second = two_users[0], two_users[1]
    sw.save_profile(first, dict(BLANK, name="First's"), expected_revision=None)
    sw.save_profile(second, dict(BLANK, name="Second's"), expected_revision=None)
    r = _call(client, _session_handle_for(second), "GET", "/v1/strategy")
    assert r.status_code == 200
    assert r.json()["profile"]["name"] == "Second's"


def test_put_writes_only_the_session_owner_even_with_a_foreign_version(
    client, two_users
):
    first, second = two_users[0], two_users[1]
    a = sw.save_profile(first, dict(BLANK, name="A"), expected_revision=None)
    handle = _session_handle_for(second)
    # The second user replays the FIRST user's version: it is not theirs.
    r = _put(client, handle, dict(BLANK, name="B"), a["updated_at"])
    assert r.status_code == 409
    assert r.json() == {"detail": "stale_profile"}
    assert strategy.get_active_strategy(first)["name"] == "A"
    assert strategy.get_active_strategy(second) is None
    # With their own (null) version the write lands on THEIR row only.
    ok = _put(client, handle, dict(BLANK, name="B"), None)
    assert ok.status_code == 200
    assert ok.json()["profile"]["name"] == "B"
    assert strategy.get_active_strategy(first)["name"] == "A"


@pytest.mark.parametrize(
    "key", ["user_id", "id", "is_active", "strategy_profile_completed", "updated_at"]
)
def test_put_with_an_ownership_or_state_key_is_422_and_writes_nothing(
    client, two_users, key
):
    second = two_users[1]
    body = dict(BLANK, name="X", expected_revision=None, **{key: 1})
    r = _call(client, _session_handle_for(second), "PUT", "/v1/strategy", body)
    assert r.status_code == 422
    assert strategy.get_active_strategy(second) is None
    assert get_onboarding_state(second)["strategy_profile_completed"] is False


def test_put_with_a_missing_field_is_422_rather_than_a_cleared_rule(client, two_users):
    second = two_users[1]
    body = dict(BLANK, name="X", expected_revision=None)
    body.pop("risk_rules")
    r = _call(client, _session_handle_for(second), "PUT", "/v1/strategy", body)
    assert r.status_code == 422
    assert strategy.get_active_strategy(second) is None


# ── Versions and bounds ───────────────────────────────────────────────────


def test_put_stale_is_409_and_the_stored_profile_is_unchanged(client, two_users):
    second = two_users[1]
    handle = _session_handle_for(second)
    first = _put(client, handle, dict(BLANK, name="v1"), None).json()
    moved = _put(client, handle, dict(BLANK, name="v2"), first["revision"]).json()
    r = _put(client, handle, dict(BLANK, name="stale tab"), first["revision"])
    assert r.status_code == 409
    assert r.json() == {"detail": "stale_profile"}
    stored = strategy.get_active_strategy(second)
    assert stored["name"] == "v2"
    assert stored["updated_at"] == moved["revision"]


def test_the_version_is_the_servers_and_moves_on_every_save(client, two_users):
    second = two_users[1]
    handle = _session_handle_for(second)
    a = _put(client, handle, dict(BLANK, name="same"), None).json()
    b = _put(client, handle, dict(BLANK, name="same"), a["revision"]).json()
    assert a["revision"] and b["revision"] and a["revision"] != b["revision"]
    assert b["revision"] == strategy.get_active_strategy(second)["updated_at"]


def test_put_over_limit_is_422_naming_the_field_without_echoing_it(client, two_users):
    second = two_users[1]
    secret_text = "SENSITIVE-RULE-" + "x" * 600
    r = _put(
        client,
        _session_handle_for(second),
        dict(BLANK, name="X", entry_rules=secret_text),
        None,
    )
    assert r.status_code == 422
    assert r.json() == {"detail": [{"field": "entry_rules", "problem": "too_long"}]}
    assert "SENSITIVE-RULE" not in r.text
    assert strategy.get_active_strategy(second) is None


def test_a_legacy_over_limit_field_is_returned_intact_and_flagged(client, two_users):
    second = two_users[1]
    long_text = "legacy rule " * 60
    strategy.upsert_strategy_profile(second, name="Old", risk_rules=long_text)
    body = _call(client, _session_handle_for(second), "GET", "/v1/strategy").json()
    assert body["profile"]["risk_rules"] == long_text
    assert body["over_limit"] == ["risk_rules"]
    assert body["limits"]["risk_rules"] == 500
    assert body["limits"]["name"] == 100


# ── First run ─────────────────────────────────────────────────────────────


def test_first_save_ends_first_run(client, two_users):
    second = two_users[1]
    handle = _session_handle_for(second)
    assert _call(client, handle, "GET", "/v1/strategy").json()["first_run"] is True
    saved = _put(client, handle, dict(BLANK, name="Mine"), None).json()
    assert saved["first_run"] is False


def test_skip_ends_first_run_without_a_profile(client, two_users):
    second = two_users[1]
    handle = _session_handle_for(second)
    r = _call(client, handle, "POST", "/v1/strategy/skip", {})
    assert r.status_code == 200
    assert r.json()["first_run"] is False
    assert r.json()["profile"] is None
    assert strategy.get_active_strategy(second) is None
    assert get_onboarding_state(two_users[0])["strategy_profile_completed"] is False


# ── Insights ──────────────────────────────────────────────────────────────


def test_another_owners_repeat_is_404_byte_identical_to_an_unknown_one(
    client, two_users
):
    first, second = two_users[0], two_users[1]
    _repeat(first)  # the FIRST user's repeated correction
    p = sw.save_profile(second, dict(BLANK, name="Mine"), expected_revision=None)
    handle = _session_handle_for(second)
    foreign = _call(
        client,
        handle,
        "POST",
        "/v1/strategy/insights",
        {
            "field": "bias",
            "user_value": "bearish",
            "expected_revision": p["updated_at"],
        },
    )
    unknown = _call(
        client,
        handle,
        "POST",
        "/v1/strategy/insights",
        {"field": "nope", "user_value": "nope", "expected_revision": p["updated_at"]},
    )
    assert foreign.status_code == unknown.status_code == 404
    assert foreign.content == unknown.content
    assert strategy.get_active_strategy(second)["risk_rules"] is None


@pytest.mark.parametrize("key", ["target", "into", "risk_rules", "rule"])
def test_the_insight_body_cannot_choose_a_column_or_supply_text(client, two_users, key):
    second = two_users[1]
    _repeat(second)
    p = sw.save_profile(second, dict(BLANK, name="Mine"), expected_revision=None)
    r = _call(
        client,
        _session_handle_for(second),
        "POST",
        "/v1/strategy/insights",
        {
            "field": "bias",
            "user_value": "bearish",
            "expected_revision": p["updated_at"],
            key: "entry_rules",
        },
    )
    assert r.status_code == 422
    assert strategy.get_active_strategy(second)["risk_rules"] is None


def test_an_insight_is_added_to_risk_rules_and_then_no_longer_suggested(
    client, two_users
):
    second = two_users[1]
    _repeat(second)
    handle = _session_handle_for(second)
    p = _put(client, handle, dict(BLANK, name="Mine"), None).json()
    assert [(s["rule"], s["count"]) for s in p["suggestions"]] == [(RULE, 5)]
    body = {
        "field": "bias",
        "user_value": "bearish",
        "expected_revision": p["revision"],
    }
    out = _call(client, handle, "POST", "/v1/strategy/insights", body)
    assert out.status_code == 200
    assert out.json()["profile"]["risk_rules"] == RULE
    assert out.json()["suggestions"] == []
    # A double-click replays the same body: a no-op, not a 409.
    again = _call(client, handle, "POST", "/v1/strategy/insights", body)
    assert again.status_code == 200
    assert again.json()["revision"] == out.json()["revision"]


@pytest.mark.parametrize(
    "setup, detail",
    [("none", "no_profile"), ("full", "rules_full"), ("stale", "stale_profile")],
)
def test_insight_refusals_are_409_with_a_fixed_code(client, two_users, setup, detail):
    second = two_users[1]
    _repeat(second)
    revision = None
    if setup == "full":
        p = sw.save_profile(
            second, dict(BLANK, name="M", risk_rules="x" * 490), expected_revision=None
        )
        revision = p["updated_at"]
    elif setup == "stale":
        p = sw.save_profile(second, dict(BLANK, name="M"), expected_revision=None)
        sw.save_profile(
            second, dict(BLANK, name="M2"), expected_revision=p["updated_at"]
        )
        revision = p["updated_at"]
    r = _call(
        client,
        _session_handle_for(second),
        "POST",
        "/v1/strategy/insights",
        {"field": "bias", "user_value": "bearish", "expected_revision": revision},
    )
    assert r.status_code == 409
    assert r.json() == {"detail": detail}


# ── What the page reads ───────────────────────────────────────────────────


def test_the_starter_is_the_service_template_and_is_not_saved(client, two_users):
    second = two_users[1]
    body = _call(client, _session_handle_for(second), "GET", "/v1/strategy").json()
    assert body["starter"] == dict(BLANK, **dict(STARTER_TEMPLATE))
    assert body["profile"] is None
    assert strategy.get_active_strategy(second) is None


def test_sections_and_counts_are_the_servers_completion(client, two_users):
    second = two_users[1]
    profile = dict(
        BLANK, name="Mine", stop_rules="Behind the OB", setups_avoided="News candles"
    )
    sw.save_profile(second, profile, expected_revision=None)
    body = _call(client, _session_handle_for(second), "GET", "/v1/strategy").json()
    # The server's own function AND a hand-counted expectation, so the test
    # cannot be right about the wrong constant.
    assert (body["written"], body["total"]) == profile_completion(profile) == (3, 6)
    assert [(s["id"], s["written"]) for s in body["sections"]] == [
        ("identity", True),
        ("entry", False),
        ("exit", True),
        ("risk", False),
        ("setups", True),
        ("self_awareness", False),
    ]


def test_facets_come_from_the_existing_parsers(client, two_users):
    second = two_users[1]
    sw.save_profile(
        second,
        dict(BLANK, name="M", markets="nq, ES", timeframes="1m entry, 15m HTF"),
        expected_revision=None,
    )
    body = _call(client, _session_handle_for(second), "GET", "/v1/strategy").json()
    assert body["facets"] == {
        "markets": ["NQ", "ES"],
        "entry_timeframe": "1m",
        "htf_timeframe": "15m",
        "setups": [],
    }


# ── The boundary ──────────────────────────────────────────────────────────

ROUTES = [
    ("GET", "/v1/strategy", None),
    ("PUT", "/v1/strategy", dict(BLANK, name="X", expected_revision=None)),
    ("POST", "/v1/strategy/skip", {}),
    (
        "POST",
        "/v1/strategy/insights",
        {"field": "bias", "user_value": "bearish", "expected_revision": None},
    ),
]


@pytest.mark.parametrize("method, path, payload", ROUTES)
def test_every_route_needs_the_signature(client, two_users, method, path, payload):
    handle = _session_handle_for(two_users[1])
    r = _call(client, handle, method, path, payload, sign=False)
    assert r.status_code == 401
    assert get_onboarding_state(two_users[1])["strategy_profile_completed"] is False


@pytest.mark.parametrize("method, path, payload", ROUTES)
def test_every_route_needs_a_live_session(client, two_users, method, path, payload):
    for handle in (None, "0" * 64):
        r = _call(client, handle, method, path, payload)
        assert r.status_code == 401
    assert strategy.get_active_strategy(two_users[0]) is None
    assert strategy.get_active_strategy(two_users[1]) is None


def test_the_response_schema_rejects_drift(client, two_users):
    body = _call(
        client, _session_handle_for(two_users[1]), "GET", "/v1/strategy"
    ).json()
    StrategyResponse.model_validate(body)
    with pytest.raises(Exception):
        StrategyResponse.model_validate(dict(body, surprise=True))
    renamed = dict(body)
    renamed["sections_written"] = renamed.pop("written")
    with pytest.raises(Exception):
        StrategyResponse.model_validate(renamed)
