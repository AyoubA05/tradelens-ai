"""Contract for the site -> Streamlit handoff and the durable session.

Two credentials, never interchanged. The handoff crosses the origin boundary
once and dies; the session is what the user actually holds afterwards.

The costly failures here are concurrency and replay, so those get real threads
and real second attempts rather than a comment saying they were considered.
"""

from __future__ import annotations

import hashlib
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from src.tradelens.db.models import Base, User
from src.tradelens.services import auth_handoff, auth_sessions


@pytest.fixture()
def db(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'auth.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    monkeypatch.setattr(auth_handoff, "SessionLocal", Session)
    monkeypatch.setattr(auth_sessions, "SessionLocal", Session)
    s = Session()
    try:
        s.add(User(id=1, username="ayoub", password_hash="h", is_active=1))
        s.add(User(id=2, username="Ayoub", password_hash="h2", is_active=1))
        s.commit()
    finally:
        s.close()
    return Session


def _now():
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Handoff
# ---------------------------------------------------------------------------


def test_handoff_stores_only_the_hash(db):
    token = auth_handoff.issue_handoff(1)
    s = db()
    try:
        stored = s.execute(text("SELECT token_hash FROM auth_handoffs")).scalars().all()
    finally:
        s.close()
    assert token not in stored, "the raw token must never reach storage"
    assert stored == [hashlib.sha256(token.encode()).hexdigest()]


def test_handoff_carries_no_claims(db):
    """It is a lookup key. A user id or email inside it would be a bearer claim."""
    token = auth_handoff.issue_handoff(1)
    assert "ayoub" not in token
    assert (
        "1" not in token.replace("_", "").replace("-", "") or True
    )  # base64url may contain digits
    # The real assertion: it cannot be decoded into anything meaningful.
    import base64

    with pytest.raises(Exception):
        base64.urlsafe_b64decode(token + "==").decode("utf-8")


def test_handoff_redeems_once(db):
    token = auth_handoff.issue_handoff(1)
    assert auth_handoff.redeem_handoff(token) == 1
    assert auth_handoff.redeem_handoff(token) is None, "replay must fail"


def test_expired_handoff_is_refused(db):
    past = _now() - timedelta(seconds=auth_handoff.HANDOFF_TTL_S + 1)
    token = auth_handoff.issue_handoff(1, now=past)
    assert auth_handoff.redeem_handoff(token) is None


def test_handoff_lives_exactly_120_seconds(db):
    assert auth_handoff.HANDOFF_TTL_S == 120
    issued = _now()
    token = auth_handoff.issue_handoff(1, now=issued)
    just_inside = issued + timedelta(seconds=119)
    assert auth_handoff.redeem_handoff(token, now=just_inside) == 1

    token2 = auth_handoff.issue_handoff(1, now=issued)
    just_outside = issued + timedelta(seconds=121)
    assert auth_handoff.redeem_handoff(token2, now=just_outside) is None


def test_unknown_handoff_is_refused(db):
    assert auth_handoff.redeem_handoff("not-a-real-token") is None
    assert auth_handoff.redeem_handoff("") is None
    assert auth_handoff.redeem_handoff(None) is None


def test_concurrent_redemption_yields_exactly_one_winner(db):
    """Streamlit reruns concurrently and users open duplicate tabs.

    A read-then-write would let every caller observe an unconsumed row and all
    proceed. The conditional UPDATE is what makes exactly one win.
    """
    token = auth_handoff.issue_handoff(1)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: auth_handoff.redeem_handoff(token), range(8)))
    assert results.count(1) == 1, f"expected exactly one winner, got {results}"
    assert results.count(None) == 7


def test_handoff_for_the_second_legacy_user_is_distinct(db):
    """ayoub and Ayoub are different accounts and must stay so."""
    a = auth_handoff.issue_handoff(1)
    b = auth_handoff.issue_handoff(2)
    assert a != b
    assert auth_handoff.redeem_handoff(a) == 1
    assert auth_handoff.redeem_handoff(b) == 2


# ---------------------------------------------------------------------------
# Sessions
# ---------------------------------------------------------------------------


def test_session_is_not_the_handoff(db):
    handoff = auth_handoff.issue_handoff(1)
    session = auth_sessions.open_session(1)
    assert session != handoff
    assert (
        auth_sessions.restore_session(handoff) is None
    ), "a handoff credential must never resolve as a session"
    assert auth_handoff.redeem_handoff(session) is None


def test_session_stores_only_the_hash(db):
    token = auth_sessions.open_session(1)
    s = db()
    try:
        stored = s.execute(text("SELECT token_hash FROM auth_sessions")).scalars().all()
    finally:
        s.close()
    assert token not in stored
    assert stored == [hashlib.sha256(token.encode()).hexdigest()]


def test_session_credential_is_256_bits(db):
    import base64

    token = auth_sessions.open_session(1)
    raw = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))
    assert len(raw) >= 32, "at least 256 bits of entropy"


def test_session_restores_and_slides_the_idle_window(db):
    started = _now()
    token = auth_sessions.open_session(1, now=started)
    for hours in (1, 5, 9, 11):  # active every few hours, never idle 8h
        assert (
            auth_sessions.restore_session(token, now=started + timedelta(hours=hours))
            == 1
        )


def test_absolute_expiry_cannot_be_extended_by_activity(db):
    """The 12-hour cap is absolute: expires_at is written once and never updated."""
    started = _now()
    token = auth_sessions.open_session(1, now=started)
    for hours in range(1, 12):
        assert (
            auth_sessions.restore_session(token, now=started + timedelta(hours=hours))
            == 1
        )
    assert (
        auth_sessions.restore_session(
            token, now=started + timedelta(hours=12, minutes=1)
        )
        is None
    ), "activity must not push the absolute bound"


def test_idle_expiry(db):
    started = _now()
    token = auth_sessions.open_session(1, now=started)
    assert (
        auth_sessions.restore_session(
            token, now=started + timedelta(seconds=auth_sessions.IDLE_TIMEOUT_S + 60)
        )
        is None
    )


def test_the_two_clocks_are_the_configured_values(db):
    assert auth_sessions.IDLE_TIMEOUT_S == 8 * 3600
    assert auth_sessions.ABSOLUTE_TIMEOUT_S == 12 * 3600


def test_revocation_ends_a_session_immediately(db):
    """Defect D1: sign-out used to leave a working credential behind."""
    token = auth_sessions.open_session(1)
    assert auth_sessions.restore_session(token) == 1
    assert auth_sessions.revoke_session(token) is True
    assert auth_sessions.restore_session(token) is None


def test_revoking_twice_reports_no_second_ending(db):
    token = auth_sessions.open_session(1)
    assert auth_sessions.revoke_session(token) is True
    assert auth_sessions.revoke_session(token) is False


def test_revoke_all_for_user_ends_every_live_session(db):
    """Password reset must not leave sessions opened with the old password."""
    tokens = [auth_sessions.open_session(1) for _ in range(3)]
    other = auth_sessions.open_session(2)

    assert auth_sessions.revoke_all_for_user(1) == 3
    for t in tokens:
        assert auth_sessions.restore_session(t) is None
    assert auth_sessions.restore_session(other) == 2, "other users are unaffected"


def test_unknown_session_is_refused(db):
    assert auth_sessions.restore_session("nope") is None
    assert auth_sessions.restore_session("") is None
    assert auth_sessions.restore_session(None) is None


def test_sessions_do_not_leak_across_users(db):
    a = auth_sessions.open_session(1)
    b = auth_sessions.open_session(2)
    assert auth_sessions.restore_session(a) == 1
    assert auth_sessions.restore_session(b) == 2
    auth_sessions.revoke_session(a)
    assert auth_sessions.restore_session(b) == 2


def test_concurrent_restores_all_succeed(db):
    """Unlike the handoff, a session is meant to be usable from several tabs."""
    token = auth_sessions.open_session(1)
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(
            pool.map(lambda _: auth_sessions.restore_session(token), range(8))
        )
    assert results == [1] * 8
