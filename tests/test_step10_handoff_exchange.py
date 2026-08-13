"""Step 10: atomic handoff exchange, Streamlit entry, and routing.

The most valuable test here is the rollback one. The obvious two-commit
implementation — redeem the handoff, then create the session — leaves a window
where the token is permanently burned and no session exists, and a user who hits
it cannot recover: the handoff is single-use, so retrying fails too. These tests
force a failure inside the exchange and prove the handoff survives it.
"""

from __future__ import annotations

import hashlib
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from src.tradelens.db.models import Base, User
from src.tradelens.services import auth_exchange, auth_handoff, auth_sessions, users
from src.tradelens.ui.components import site_auth, strategy_gate


@pytest.fixture()
def db(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'step10.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    # users too: the strategy gate reads onboarding flags through it.
    for module in (auth_exchange, auth_handoff, auth_sessions, users):
        monkeypatch.setattr(module, "SessionLocal", Session)
    s = Session()
    try:
        s.add(
            User(
                id=1,
                username="u_ready",
                password_hash="h",
                is_active=1,
                onboarding_completed=True,
                strategy_profile_completed=False,
                email_verification_required=False,
            )
        )
        s.add(
            User(
                id=2,
                username="u_other",
                password_hash="h",
                is_active=1,
                onboarding_completed=True,
                strategy_profile_completed=True,
                email_verification_required=False,
            )
        )
        s.commit()
    finally:
        s.close()
    return Session


class FakeQueryParams(dict):
    """Enough of st.query_params for the entry-path tests."""

    def pop(self, key, default=None):  # noqa: A003 - mirrors the real API
        return super().pop(key, default)


class FakeStreamlit:
    def __init__(self, **params):
        self.query_params = FakeQueryParams(params)
        self.session_state = {}


# ---------------------------------------------------------------------------
# Atomic exchange
# ---------------------------------------------------------------------------


def test_valid_handoff_exchanges(db):
    ht = auth_handoff.issue_handoff(1)
    token = auth_exchange.exchange_handoff_for_streamlit_session(ht)
    assert token is not None
    assert auth_sessions.restore_streamlit_session(token) == 1


def test_the_new_credential_is_not_the_handoff(db):
    ht = auth_handoff.issue_handoff(1)
    token = auth_exchange.exchange_handoff_for_streamlit_session(ht)
    assert token != ht
    # And the handoff cannot act as a session, nor the session as a handoff.
    assert auth_sessions.restore_streamlit_session(ht) is None
    assert auth_handoff.redeem_handoff(token) is None


def test_only_the_streamlit_domain_hash_is_stored(db):
    ht = auth_handoff.issue_handoff(1)
    token = auth_exchange.exchange_handoff_for_streamlit_session(ht)
    s = db()
    try:
        stored, surface = s.execute(
            text("SELECT token_hash, surface FROM auth_sessions")
        ).one()
    finally:
        s.close()
    assert surface == "streamlit"
    assert (
        stored
        == hashlib.sha256(
            (auth_sessions.STREAMLIT_DOMAIN + token).encode("utf-8")
        ).hexdigest()
    )
    assert stored != hashlib.sha256(token.encode()).hexdigest()
    assert token not in stored


def test_exactly_one_session_is_created(db):
    ht = auth_handoff.issue_handoff(1)
    auth_exchange.exchange_handoff_for_streamlit_session(ht)
    s = db()
    try:
        assert s.execute(text("SELECT count(*) FROM auth_sessions")).scalar() == 1
    finally:
        s.close()


@pytest.mark.parametrize("bad", [None, "", 42, "not-a-real-token", b"bytes"])
def test_malformed_or_unknown_handoffs_are_refused(db, bad):
    assert auth_exchange.exchange_handoff_for_streamlit_session(bad) is None


def test_expired_handoff_refused(db):
    from datetime import datetime, timedelta, timezone

    past = datetime.now(timezone.utc) - timedelta(
        seconds=auth_handoff.HANDOFF_TTL_S + 5
    )
    ht = auth_handoff.issue_handoff(1, now=past)
    assert auth_exchange.exchange_handoff_for_streamlit_session(ht) is None


def test_consumed_handoff_refused(db):
    ht = auth_handoff.issue_handoff(1)
    assert auth_exchange.exchange_handoff_for_streamlit_session(ht) is not None
    assert auth_exchange.exchange_handoff_for_streamlit_session(ht) is None


def test_consume_and_insert_share_one_transaction(db):
    """Both statements commit together, or neither does."""
    ht = auth_handoff.issue_handoff(1)
    auth_exchange.exchange_handoff_for_streamlit_session(ht)
    s = db()
    try:
        consumed = s.execute(text("SELECT consumed_at FROM auth_handoffs")).scalar()
        sessions = s.execute(text("SELECT count(*) FROM auth_sessions")).scalar()
    finally:
        s.close()
    assert consumed is not None
    assert sessions == 1


def test_session_insert_failure_rolls_back_the_consume(db, monkeypatch):
    """The invariant that motivates the whole design.

    A forced failure during session creation must leave the handoff redeemable —
    otherwise a transient database error permanently destroys a valid sign-in
    link and the user has no way to recover it.
    """
    ht = auth_handoff.issue_handoff(1)

    # Patch _session_hash, which runs *inside* the transaction after the handoff
    # has already been marked consumed. Patching the token generator instead
    # would fire before any database work and prove nothing about rollback.
    real_hash = auth_exchange._session_hash
    failing = {"on": True}

    def explode(token: str) -> str:
        if failing["on"]:
            raise RuntimeError("session insert failed")
        return real_hash(token)

    monkeypatch.setattr(auth_exchange, "_session_hash", explode)
    with pytest.raises(RuntimeError):
        auth_exchange.exchange_handoff_for_streamlit_session(ht)

    # Disabled by flag rather than monkeypatch.undo(), which would also revert
    # the fixture's SessionLocal patches and point the next call at the real
    # database.
    failing["on"] = False
    s = db()
    try:
        assert s.execute(text("SELECT consumed_at FROM auth_handoffs")).scalar() is None
        assert s.execute(text("SELECT count(*) FROM auth_sessions")).scalar() == 0
    finally:
        s.close()

    # And it still works afterwards.
    assert auth_exchange.exchange_handoff_for_streamlit_session(ht) is not None


def test_duplicate_session_token_rolls_back_the_consume(db, monkeypatch):
    """A unique violation on insert is a real failure mode, not a synthetic one."""
    first = auth_handoff.issue_handoff(1)
    fixed = auth_exchange._new_session_token()
    monkeypatch.setattr(auth_exchange, "_new_session_token", lambda: fixed)

    assert auth_exchange.exchange_handoff_for_streamlit_session(first) is not None

    second = auth_handoff.issue_handoff(1)
    with pytest.raises(Exception):
        auth_exchange.exchange_handoff_for_streamlit_session(second)

    s = db()
    try:
        unconsumed = s.execute(
            text("SELECT count(*) FROM auth_handoffs WHERE consumed_at IS NULL")
        ).scalar()
    finally:
        s.close()
    assert unconsumed == 1, "the second handoff must survive the failed insert"


def test_concurrent_exchange_of_one_handoff_yields_one_winner(db):
    ht = auth_handoff.issue_handoff(1)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(
            pool.map(
                lambda _: auth_exchange.exchange_handoff_for_streamlit_session(ht),
                range(8),
            )
        )
    winners = [r for r in results if r is not None]
    assert len(winners) == 1, f"expected one winner, got {len(winners)}"

    s = db()
    try:
        assert s.execute(text("SELECT count(*) FROM auth_sessions")).scalar() == 1
    finally:
        s.close()


# ---------------------------------------------------------------------------
# Eligibility re-checked at exchange time
# ---------------------------------------------------------------------------


def _set(db, user_id, **fields):
    s = db()
    try:
        assignments = ", ".join(f"{k} = :{k}" for k in fields)
        s.execute(
            text(f"UPDATE users SET {assignments} WHERE id = :i"),
            {**fields, "i": user_id},
        )
        s.commit()
    finally:
        s.close()


def test_inactive_user_cannot_exchange(db):
    ht = auth_handoff.issue_handoff(1)
    _set(db, 1, is_active=0)
    assert auth_exchange.exchange_handoff_for_streamlit_session(ht) is None


def test_onboarding_incomplete_user_cannot_exchange(db):
    ht = auth_handoff.issue_handoff(1)
    _set(db, 1, onboarding_completed=False)
    assert auth_exchange.exchange_handoff_for_streamlit_session(ht) is None


def test_unverified_user_cannot_exchange(db):
    ht = auth_handoff.issue_handoff(1)
    _set(db, 1, email_verification_required=True, email_verified_at=None)
    assert auth_exchange.exchange_handoff_for_streamlit_session(ht) is None


def test_strategy_profile_incomplete_user_CAN_exchange(db):
    """The whole point: that false is what routes them to the first-run profile.

    Requiring it would make the screen that sets it unreachable.
    """
    _set(db, 1, strategy_profile_completed=False)
    ht = auth_handoff.issue_handoff(1)
    assert auth_exchange.exchange_handoff_for_streamlit_session(ht) is not None


def test_eligibility_is_rechecked_not_trusted_from_issuance(db):
    """A handoff lives 120 seconds; an account can change inside that window."""
    ht = auth_handoff.issue_handoff(1)
    _set(db, 1, is_active=0)
    assert auth_exchange.exchange_handoff_for_streamlit_session(ht) is None
    _set(db, 1, is_active=1)
    assert auth_exchange.exchange_handoff_for_streamlit_session(ht) is not None


# ---------------------------------------------------------------------------
# Streamlit entry path
# ---------------------------------------------------------------------------


def test_handoff_param_becomes_session_param(db):
    ht = auth_handoff.issue_handoff(1)
    st = FakeStreamlit(ht=ht)
    assert site_auth.authenticate(st) == 1
    assert "ht" not in st.query_params, "the spent one-time credential must be gone"
    assert st.query_params.get("s"), "the durable credential must be present"
    assert st.query_params["s"] != ht


def test_both_parameters_are_never_visible_together(db):
    ht = auth_handoff.issue_handoff(1)
    st = FakeStreamlit(ht=ht)
    site_auth.authenticate(st)
    assert set(st.query_params) == {"s"}


def test_a_valid_session_param_authenticates(db):
    token = auth_sessions.open_streamlit_session(1)
    st = FakeStreamlit(s=token)
    assert site_auth.authenticate(st) == 1


def test_a_revoked_session_param_is_refused_and_stripped(db):
    token = auth_sessions.open_streamlit_session(1)
    auth_sessions.revoke_streamlit_session(token)
    st = FakeStreamlit(s=token)
    assert site_auth.authenticate(st) is None
    assert "s" not in st.query_params


def test_an_invalid_session_cannot_inherit_stale_authenticated_state(db):
    """st.session_state survives reruns; a revoked credential must not.

    Without clearing the runtime flags, a session that authenticated one rerun
    ago keeps rendering as authenticated after its credential dies.
    """
    token = auth_sessions.open_streamlit_session(1)
    st = FakeStreamlit(s=token)
    assert site_auth.authenticate(st) == 1
    assert site_auth.is_site_authenticated(st)

    auth_sessions.revoke_streamlit_session(token)
    assert site_auth.authenticate(st) is None
    assert not site_auth.is_site_authenticated(st)


def test_an_established_session_wins_over_a_spent_handoff(db):
    """A refresh on a URL still carrying a used ht must not report a failure."""
    ht = auth_handoff.issue_handoff(1)
    st = FakeStreamlit(ht=ht)
    site_auth.authenticate(st)
    token = st.query_params["s"]

    refreshed = FakeStreamlit(s=token, ht=ht)
    assert refreshed.query_params.get("ht") == ht
    assert site_auth.authenticate(refreshed) == 1
    assert site_auth.site_error(refreshed) is None


def test_a_failed_handoff_gives_one_generic_message_and_is_stripped(db):
    st = FakeStreamlit(ht="not-a-real-handoff")
    assert site_auth.authenticate(st) is None
    assert site_auth.site_error(st) == site_auth.INVALID_LINK_MESSAGE
    assert "ht" not in st.query_params
    assert "s" not in st.query_params


def test_a_failed_handoff_is_not_retried_on_every_rerun(db, monkeypatch):
    calls = {"n": 0}
    real = auth_exchange.exchange_handoff_for_streamlit_session

    def counting(token, *a, **k):
        calls["n"] += 1
        return real(token, *a, **k)

    monkeypatch.setattr(
        auth_exchange, "exchange_handoff_for_streamlit_session", counting
    )

    st = FakeStreamlit(ht="dead-token")
    for _ in range(5):
        st.query_params["ht"] = "dead-token"  # a stubborn URL
        site_auth.authenticate(st)
    assert calls["n"] == 1, "a spent token must not be presented to the DB every rerun"


def test_the_return_destination_is_server_configured(db, monkeypatch):
    monkeypatch.setenv("SITE_ORIGIN", "https://www.tradelensai.io")
    assert site_auth.return_to_site_url() == "https://www.tradelensai.io/login"
    # Nothing from the URL can influence it.
    st = FakeStreamlit(ht="x", next="https://evil.test")
    site_auth.authenticate(st)
    assert "evil" not in site_auth.return_to_site_url()


def test_sign_out_revokes_only_this_session(db):
    mine = auth_sessions.open_streamlit_session(1)
    other = auth_sessions.open_streamlit_session(1)
    st = FakeStreamlit(s=mine)
    site_auth.authenticate(st)

    assert site_auth.sign_out_streamlit_session(st) is True
    assert "s" not in st.query_params
    assert auth_sessions.restore_streamlit_session(mine) is None
    assert (
        auth_sessions.restore_streamlit_session(other) == 1
    ), "sign-out must not become sign-out-everywhere"


def test_the_stable_query_params_api_is_used():
    """Streamlit 1.50 has stable st.query_params; the experimental API is not used."""
    import inspect

    source = inspect.getsource(site_auth)
    assert "st.query_params" in source
    assert "experimental_get_query_params" not in source
    assert "experimental_set_query_params" not in source


def test_no_credential_is_logged(db, caplog):
    import logging

    caplog.set_level(logging.DEBUG)
    ht = auth_handoff.issue_handoff(1)
    st = FakeStreamlit(ht=ht)
    site_auth.authenticate(st)
    token = st.query_params["s"]
    site_auth.sign_out_streamlit_session(st)

    assert ht not in caplog.text
    assert token not in caplog.text
    assert "query_params" not in caplog.text


# ---------------------------------------------------------------------------
# Strategy Profile routing
# ---------------------------------------------------------------------------


def test_incomplete_profile_routes_to_the_first_run_flow(db):
    assert strategy_gate.needs_strategy_profile(1) is True
    assert strategy_gate.route_after_authentication(1) == "strategy_profile"


def test_completed_profile_routes_to_the_dashboard(db):
    assert strategy_gate.needs_strategy_profile(2) is False
    assert strategy_gate.route_after_authentication(2) == "dashboard"


def test_authenticating_does_not_complete_the_profile(db):
    ht = auth_handoff.issue_handoff(1)
    auth_exchange.exchange_handoff_for_streamlit_session(ht)
    s = db()
    try:
        completed = s.execute(
            text("SELECT strategy_profile_completed FROM users WHERE id = 1")
        ).scalar()
    finally:
        s.close()
    assert not completed
    assert strategy_gate.route_after_authentication(1) == "strategy_profile"


def test_routing_reads_the_database_not_the_url(db):
    """A query parameter must not be able to skip the first-run step."""
    import inspect

    source = inspect.getsource(strategy_gate)
    assert "query_params" not in source
    assert "get_onboarding_state" in source


def test_a_legacy_null_user_id_is_never_routed_to_the_profile(db):
    # Legacy bootstrap sessions carry user_id None and own no Strategy rows.
    assert strategy_gate.needs_strategy_profile(None) is False
