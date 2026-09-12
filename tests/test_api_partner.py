"""`/v1/partner/turns` and `/v1/trades/{id}/partner/turns`.

The conversation is browser-held, so these tests care about who can spend,
what a refusal reveals, and whether a turn returned by one request is accepted
by the next. Isolation tests authenticate the SECOND user: the
`website_session_handle` fixture is always user 1 and is blind to a route
that hardcodes `user_id=1`.
"""

from __future__ import annotations

import base64
import dataclasses
import datetime as dt
import hashlib
import json
import secrets
import time
import types

import pytest
from fastapi.testclient import TestClient

from src.tradelens.api.app import create_app
from src.tradelens.api.schemas.partner import PartnerTurnResponse
from src.tradelens.api.security import sign_request
from src.tradelens.db.models import Screenshot, Trade
from src.tradelens.db.session import SessionLocal
from src.tradelens.services import partner, partner_transcript as pt, partner_turns

SECRET = "test-service-secret-value-at-least-32-bytes"
GLOBAL = "/v1/partner/turns"
REPLY = "Reviewing the completed trade: your exit left R on the table."
QUESTION = "Did I follow my own rules on that one?"


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


@pytest.fixture(autouse=True)
def provider(monkeypatch):
    """No network, and a reply that passes the scope guard."""
    calls = []

    def fake(messages, **kw):
        calls.append({"messages": messages, **kw})
        if kw.get("on_usage") is not None:
            kw["on_usage"](None)
        return REPLY, None

    monkeypatch.setattr(partner, "partner_reply", fake)
    return calls


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


def _call(client, handle, path, payload, *, sign=True):
    body = b"" if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if sign:
        ts = str(int(time.time()))
        headers["X-TL-Signature"] = "v1={}:{}".format(
            ts, sign_request(SECRET, ts, "POST", path, "", body)
        )
    if handle is not None:
        headers["X-TL-Session-Handle"] = handle
    return client.request("POST", path, content=body, headers=headers)


def _body(question=QUESTION, n=1, **over):
    payload = {
        "question": question,
        "conversation_id": None,
        "transcript": [],
        "client_turn_id": "client-turn-%010d" % n,
    }
    payload.update(over)
    return payload


def _trade(owner, **over):
    db = SessionLocal()
    try:
        row = Trade(user_id=owner, asset="NQ", direction="Long", result="Win", **over)
        db.add(row)
        db.commit()
        return row.id
    finally:
        db.close()


def _trade_path(trade_id):
    return "/v1/trades/{}/partner/turns".format(trade_id)


PNG = b"\x89PNG\r\n\x1a\n" + b"partner-screenshot-bytes"


def _screenshot(trade_id):
    db = SessionLocal()
    try:
        row = Screenshot(trade_id=trade_id, file_path="users/x/trades/y/final.png")
        db.add(row)
        db.commit()
        return row.id
    finally:
        db.close()


def _wire_turn(idx, **over):
    """A turn shaped like the wire contract — NOT one the chain would accept.

    Only for tests that must be refused by the schema, which runs long before
    any signature is checked.
    """
    turn = {
        "idx": idx,
        "role": "user",
        "text": "t",
        "iat": 1_700_000_000 + idx,
        "mac": "a" * 64,
    }
    turn.update(over)
    return turn


# ── both locks ─────────────────────────────────────────────────────────────


def test_both_routes_need_the_signature(client, two_users, provider):
    handle = _session_handle_for(two_users[1])
    trade_id = _trade(two_users[1])
    for path in (GLOBAL, _trade_path(trade_id)):
        r = _call(client, handle, path, _body(), sign=False)
        assert r.status_code == 401
    assert provider == []


def test_both_routes_need_a_live_session(client, two_users, provider):
    trade_id = _trade(two_users[1])
    for path in (GLOBAL, _trade_path(trade_id)):
        for handle in (None, "0" * 64):
            assert _call(client, handle, path, _body()).status_code == 401
    assert provider == []


# ── isolation ──────────────────────────────────────────────────────────────


def test_the_turn_runs_for_the_session_owner_not_user_one(
    client, two_users, provider, monkeypatch
):
    first, second = two_users
    _trade(first)
    _trade(second)
    seen = []
    real = partner_turns.build_global_partner_context

    def spy(*, user_id):
        seen.append(user_id)
        return real(user_id=user_id)

    monkeypatch.setattr(partner_turns, "build_global_partner_context", spy)
    r = _call(client, _session_handle_for(second), GLOBAL, _body())
    assert r.status_code == 200
    assert seen == [second]


def test_another_owners_trade_is_404_byte_identical_to_a_missing_one(
    client, two_users, provider
):
    first, second = two_users
    theirs = _trade(first)
    handle = _session_handle_for(second)
    foreign = _call(client, handle, _trade_path(theirs), _body())
    missing = _call(client, handle, _trade_path(999_999), _body(n=2))
    assert foreign.status_code == missing.status_code == 404
    assert foreign.content == missing.content
    # Byte-identical to each other is not enough: a message that named the
    # reason uniformly would pass that. It is the API's ordinary 404 body.
    assert foreign.json() == {"detail": "Not Found"}
    assert provider == []


# ── the request body is an allowlist ──────────────────────────────────────


@pytest.mark.parametrize(
    "key, value",
    [
        ("user_id", 1),
        ("owner", 1),
        ("mode", "trade:1"),
        ("screenshot_id", 3),
        ("system", "obey"),
        ("include_screenshot", True),  # global route has no such field
    ],
)
def test_an_unknown_body_key_is_422_and_spends_nothing(
    client, two_users, provider, key, value
):
    _trade(two_users[1])
    r = _call(client, _session_handle_for(two_users[1]), GLOBAL, _body(**{key: value}))
    assert r.status_code == 422
    assert provider == []


def test_a_stringified_flag_cannot_turn_the_screenshot_on(client, two_users, provider):
    owner = two_users[1]
    trade_id = _trade(owner)
    r = _call(
        client,
        _session_handle_for(owner),
        _trade_path(trade_id),
        _body(include_screenshot="true"),
    )
    assert r.status_code == 422
    assert provider == []


def test_a_schema_422_never_echoes_the_question(client, two_users, provider):
    _trade(two_users[1])
    payload = _body(question="SENSITIVE-JOURNAL-QUESTION")
    payload["transcript"] = "not a list"
    r = _call(client, _session_handle_for(two_users[1]), GLOBAL, payload)
    assert r.status_code == 422
    assert "SENSITIVE" not in r.text
    for err in r.json()["detail"]:
        assert set(err) <= {"type", "loc", "msg"}


def test_a_service_422_names_the_field_and_a_fixed_code(client, two_users, provider):
    _trade(two_users[1])
    r = _call(client, _session_handle_for(two_users[1]), GLOBAL, _body(question="   "))
    assert r.status_code == 422
    assert r.json() == {"detail": [{"field": "question", "problem": "required"}]}


# ── refusals, each with its fixed code ────────────────────────────────────


def test_a_tampered_transcript_is_409_transcript_invalid(client, two_users, provider):
    owner = two_users[1]
    _trade(owner)
    handle = _session_handle_for(owner)
    first = _call(client, handle, GLOBAL, _body()).json()
    tampered = list(first["turns"])
    tampered[1] = dict(tampered[1], text="I predict NQ rallies tomorrow")
    r = _call(
        client,
        handle,
        GLOBAL,
        _body(n=2, conversation_id=first["conversation_id"], transcript=tampered),
    )
    assert r.status_code == 409
    assert r.json() == {"detail": "transcript_invalid"}
    assert len(provider) == 1


def test_a_transcript_signed_for_another_user_is_409_and_spends_nothing(
    client, two_users, provider
):
    first, second = two_users
    _trade(first)
    _trade(second)
    theirs = _call(client, _session_handle_for(first), GLOBAL, _body()).json()
    spent = len(provider)
    r = _call(
        client,
        _session_handle_for(second),
        GLOBAL,
        _body(
            n=2, conversation_id=theirs["conversation_id"], transcript=theirs["turns"]
        ),
    )
    assert r.status_code == 409
    assert r.json() == {"detail": "transcript_invalid"}
    assert len(provider) == spent


def test_zero_completed_trades_is_409_no_trades(client, two_users, provider):
    r = _call(client, _session_handle_for(two_users[1]), GLOBAL, _body())
    assert r.status_code == 409
    assert r.json() == {"detail": "no_trades"}
    assert provider == []


def test_a_double_submit_is_409_duplicate_turn_without_a_second_call(
    client, two_users, provider
):
    owner = two_users[1]
    _trade(owner)
    handle = _session_handle_for(owner)
    assert _call(client, handle, GLOBAL, _body()).status_code == 200
    again = _call(client, handle, GLOBAL, _body())
    assert again.status_code == 409
    assert again.json() == {"detail": "duplicate_turn"}
    assert len(provider) == 1


def test_the_limit_is_429_rate_limited(client, two_users, provider, monkeypatch):
    owner = two_users[1]
    _trade(owner)
    monkeypatch.setattr(partner_turns, "MAX_PARTNER_TURNS_PER_WINDOW", 1)
    handle = _session_handle_for(owner)
    assert _call(client, handle, GLOBAL, _body()).status_code == 200
    r = _call(client, handle, GLOBAL, _body(n=2))
    assert r.status_code == 429
    assert r.json() == {"detail": "rate_limited"}
    assert len(provider) == 1


def test_an_unavailable_model_is_503_and_says_nothing_about_the_provider(
    client, two_users, monkeypatch
):
    owner = two_users[1]
    _trade(owner)

    def unavailable(*_a, **_k):
        raise partner.PartnerError("upstream 500 from https://api.internal/v1/messages")

    monkeypatch.setattr(partner, "partner_reply", unavailable)
    r = _call(client, _session_handle_for(owner), GLOBAL, _body())
    assert r.status_code == 503
    assert r.json() == {"detail": "partner_unavailable"}
    assert "api.internal" not in r.text


def test_no_route_ever_returns_driver_text(client, two_users, monkeypatch):
    owner = two_users[1]
    _trade(owner)

    def boom(*_a, **_k):
        raise RuntimeError("postgresql://user:password@db.internal/tradelens")

    monkeypatch.setattr(partner, "partner_reply", boom)
    r = _call(client, _session_handle_for(owner), GLOBAL, _body())
    assert r.status_code == 500
    assert "postgresql" not in r.text and "db.internal" not in r.text


# ── what the browser gets back ────────────────────────────────────────────


def test_the_response_turns_verify_on_the_next_request(client, two_users, provider):
    owner = two_users[1]
    _trade(owner)
    handle = _session_handle_for(owner)
    first = _call(client, handle, GLOBAL, _body()).json()
    assert [t["role"] for t in first["turns"]] == ["user", "assistant"]
    assert first["turns"][1]["text"] == REPLY

    second = _call(
        client,
        handle,
        GLOBAL,
        _body(
            question="And the exit?",
            n=2,
            conversation_id=first["conversation_id"],
            transcript=first["turns"],
        ),
    )
    assert second.status_code == 200
    assert second.json()["conversation_id"] == first["conversation_id"]
    assert [t["idx"] for t in second.json()["turns"]] == [2, 3]
    sent = provider[-1]["messages"]
    assert [m["content"] for m in sent] == [QUESTION, REPLY, "And the exit?"]


def test_the_evidence_names_the_records_the_context_was_built_from(
    client, two_users, provider
):
    from src.tradelens.services.strategy import upsert_strategy_profile

    owner = two_users[1]
    trade_id = _trade(owner, trade_date="2026-09-01", trade_process_notes="Waited.")
    # A Strategy Profile contributes a `strategy` source, which is NOT a trade
    # and must not be linked to one. Without a profile that branch never runs.
    upsert_strategy_profile(owner, name="London Killzone Playbook")
    r = _call(client, _session_handle_for(owner), GLOBAL, _body()).json()
    kinds = {e["kind"] for e in r["evidence"]}
    assert {"trade", "journal", "strategy"} <= kinds
    for item in r["evidence"]:
        if item["kind"] in ("trade", "journal"):
            assert item["trade_id"] == trade_id
        else:
            assert item["trade_id"] is None, item


def test_the_per_trade_route_asks_about_the_trade_in_the_path(
    client, two_users, provider
):
    """The path's trade id reaches the service. Both trades belong to this
    owner, so an ownership check alone cannot tell them apart."""
    owner = two_users[1]
    _trade(owner, trade_process_notes="ZZ-FIRST-TRADE-NOTE")
    asked_about = _trade(owner, trade_process_notes="ZZ-SECOND-TRADE-NOTE")
    r = _call(client, _session_handle_for(owner), _trade_path(asked_about), _body())
    assert r.status_code == 200
    context = provider[-1]["trade_context"]
    assert "ZZ-SECOND-TRADE-NOTE" in context
    assert "ZZ-FIRST-TRADE-NOTE" not in context


def test_the_per_trade_route_answers_without_evidence_and_without_a_screenshot(
    client, two_users, provider
):
    owner = two_users[1]
    trade_id = _trade(owner)
    r = _call(client, _session_handle_for(owner), _trade_path(trade_id), _body())
    assert r.status_code == 200
    body = r.json()
    assert body["evidence"] == [] and body["screenshot_attached"] is False
    assert provider[-1]["per_trade_qa"] is True


def test_the_response_schema_rejects_drift(client, two_users, provider):
    owner = two_users[1]
    _trade(owner)
    body = _call(client, _session_handle_for(owner), GLOBAL, _body()).json()
    PartnerTurnResponse.model_validate(body)
    with pytest.raises(Exception):
        PartnerTurnResponse.model_validate(dict(body, surprise=True))
    renamed = dict(body)
    renamed["messages"] = renamed.pop("turns")
    with pytest.raises(Exception):
        PartnerTurnResponse.model_validate(renamed)


def test_the_conversation_id_is_server_issued_and_unguessable(
    client, two_users, provider
):
    owner = two_users[1]
    _trade(owner)
    handle = _session_handle_for(owner)
    ids = {
        _call(client, handle, GLOBAL, _body(n=i)).json()["conversation_id"]
        for i in range(1, 4)
    }
    assert len(ids) == 3
    for conv in ids:
        assert len(conv) >= 16
        assert pt._CONV_RE.match(conv)


# ── the wire schema is a gate on its own ──────────────────────────────────
#
# The service catches every one of these too, so what follows is defence in
# depth. It is tested anyway: the schema docstring promises that a widened
# field is a loud failure, and without these a bound can be deleted from
# `schemas/partner.py` with the whole suite still green. Each case also
# asserts nothing was spent — a refusal that costs money is not a refusal.


@pytest.mark.parametrize(
    "label, over",
    [
        ("question over 2000 chars", {"question": "q" * 2001}),
        ("empty question", {"question": ""}),
        ("41 turns", {"transcript": [_wire_turn(i % 40) for i in range(41)]}),
        ("idx past the last position", {"transcript": [_wire_turn(99)]}),
        ("idx below zero", {"transcript": [_wire_turn(-1)]}),
        ("mac too short", {"transcript": [_wire_turn(0, mac="a" * 63)]}),
        ("mac too long", {"transcript": [_wire_turn(0, mac="a" * 65)]}),
        (
            "a role the chain does not define",
            {"transcript": [_wire_turn(0, role="system")]},
        ),
        ("an extra key inside a turn", {"transcript": [_wire_turn(0, user_id=1)]}),
        ("client_turn_id under 16 chars", {"client_turn_id": "short"}),
        ("client_turn_id over 64 chars", {"client_turn_id": "c" * 65}),
        ("conversation_id over 64 chars", {"conversation_id": "c" * 65}),
        ("a non-string question", {"question": 7}),
        ("a non-integer idx", {"transcript": [dict(_wire_turn(0), idx="0")]}),
    ],
)
def test_the_wire_schema_refuses_a_widened_field_before_anything_is_spent(
    client, two_users, provider, label, over
):
    del label
    owner = two_users[1]
    _trade(owner)
    r = _call(client, _session_handle_for(owner), GLOBAL, _body(**over))
    assert r.status_code == 422
    assert provider == []
    # Refused by the SCHEMA, not by the service behind it. The service also
    # refuses most of these, so without this the bound could be deleted from
    # `schemas/partner.py` and the test would still pass on the second gate.
    # Pydantic's records carry `loc`; a service refusal is {field, problem}.
    assert "loc" in r.json()["detail"][0]


def test_the_per_trade_route_refuses_a_screenshot_flag_that_is_not_a_boolean(
    client, two_users, provider
):
    """A stringified "false" is the classic way a flag turns itself on."""
    owner = two_users[1]
    trade_id = _trade(owner)
    handle = _session_handle_for(owner)
    for flag in ("true", "false", 1, 0, [], {}, "on"):
        r = _call(client, handle, _trade_path(trade_id), _body(include_screenshot=flag))
        assert r.status_code == 422, flag
    assert provider == []


# ── the screenshot flag ───────────────────────────────────────────────────


def test_asking_for_the_screenshot_attaches_the_trades_own_image(
    client, two_users, provider, monkeypatch
):
    owner = two_users[1]
    trade_id = _trade(owner)
    _screenshot(trade_id)
    monkeypatch.setattr(
        partner_turns.storage, "screenshot_belongs_to_trade", lambda *a: True
    )
    monkeypatch.setattr(
        partner_turns.storage, "read_owned_final_object", lambda *a: PNG
    )
    handle = _session_handle_for(owner)

    # Omitted means no screenshot. That default is one character in the
    # schema, and flipping it would change both spend and what leaves the
    # account, so it is asserted rather than assumed.
    r = _call(client, handle, _trade_path(trade_id), _body())
    assert r.status_code == 200
    assert r.json()["screenshot_attached"] is False
    assert provider[-1]["image_png_b64"] is None

    r = _call(
        client, handle, _trade_path(trade_id), _body(n=2, include_screenshot=True)
    )
    assert r.status_code == 200
    assert r.json()["screenshot_attached"] is True
    assert provider[-1]["image_png_b64"] == base64.b64encode(PNG).decode("ascii")


# ── the client turn id is opaque and matched exactly ──────────────────────


def test_a_case_variant_client_turn_id_is_a_different_turn(client, two_users, provider):
    """The id is the browser's own opaque string, compared byte for byte.

    Pinned in this direction deliberately: a retry of the same question must
    carry the SAME id to be recognised as the duplicate it is, and a browser
    that cannot reproduce its own id byte for byte has already lost that
    property. Nothing here normalises on the trader's behalf.
    """
    owner = two_users[1]
    _trade(owner)
    handle = _session_handle_for(owner)
    body = _body(client_turn_id="Abc-Turn-0000000001")

    assert _call(client, handle, GLOBAL, body).status_code == 200
    assert _call(client, handle, GLOBAL, body).status_code == 409
    spent = len(provider)

    lowered = dict(body, client_turn_id=body["client_turn_id"].lower())
    assert _call(client, handle, GLOBAL, lowered).status_code == 200
    assert len(provider) == spent + 1


def test_an_unlinkable_evidence_source_is_shown_without_a_link(
    client, two_users, provider, monkeypatch
):
    """Building the response runs AFTER the provider has been paid.

    A legacy or NULL `record_id` raising here would cost the trader the
    answer they just bought and hand them a 500 instead, so an unlinkable
    source loses its link rather than the whole turn.
    """
    owner = two_users[1]
    _trade(owner)
    real = partner_turns.run_global_turn

    def unlinkable(*a, **kw):
        broken = types.SimpleNamespace(
            kind="trade",
            label="A row from before the ids",
            occurred_on=None,
            record_id=None,
        )
        return dataclasses.replace(real(*a, **kw), evidence=(broken,))

    monkeypatch.setattr(partner_turns, "run_global_turn", unlinkable)
    r = _call(client, _session_handle_for(owner), GLOBAL, _body())
    assert r.status_code == 200
    assert r.json()["evidence"] == [
        {
            "kind": "trade",
            "label": "A row from before the ids",
            "occurred_on": None,
            "trade_id": None,
        }
    ]


# ── an unhandled fault is still a no-store, text-free response ────────────


def test_an_unexpected_service_fault_is_a_fixed_500_that_leaks_nothing(
    client, two_users, provider, monkeypatch
):
    owner = two_users[1]
    _trade(owner)

    def boom(*a, **kw):
        raise ValueError("postgresql://user:password@db.internal/tradelens")

    monkeypatch.setattr(partner_turns, "run_global_turn", boom)
    r = _call(client, _session_handle_for(owner), GLOBAL, _body())
    assert r.status_code == 500
    assert r.json() == {"detail": "internal_error"}
    assert "password" not in r.text
    # An authenticated route's failure must not be cacheable either, and
    # Starlette's own 500 leaves above the no-store middleware.
    assert r.headers["Cache-Control"] == "no-store, private"
