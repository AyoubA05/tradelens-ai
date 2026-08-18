"""Lock 2, Python side. Mirrors web/lib/auth/session.ts.

All five conditions are checked here rather than trusting the Next.js layer to
have checked them: a bug or compromise upstream must not by itself make the
backend act on the wrong account.
"""

import datetime as dt

import pytest
from sqlalchemy import text

from src.tradelens.db.session import SessionLocal
from src.tradelens.services import auth_sessions


def _open_website_session(user_id, *, now=None, expires_in=12 * 3600, idle_at=None):
    import hashlib
    import secrets

    started = now or dt.datetime.now(dt.timezone.utc)
    token = secrets.token_urlsafe(32)
    digest = hashlib.sha256(
        (auth_sessions.WEBSITE_DOMAIN + token).encode("utf-8")
    ).hexdigest()
    db = SessionLocal()
    try:
        db.execute(
            text(
                "INSERT INTO auth_sessions (token_hash, user_id, created_at, "
                "expires_at, last_seen_at, surface) VALUES (:h,:u,:c,:e,:l,:s)"
            ),
            {
                "h": digest,
                "u": user_id,
                "c": started,
                "e": started + dt.timedelta(seconds=expires_in),
                "l": idle_at or started,
                "s": auth_sessions.SURFACE_WEBSITE,
            },
        )
        db.commit()
    finally:
        db.close()
    return token


def test_a_live_session_resolves_to_its_user(two_users):
    a, _ = two_users
    token = _open_website_session(a)
    assert auth_sessions.restore_website_session(token) == a


def test_a_domain_separated_handle_resolves_without_forwarding_the_raw_token(two_users):
    a, _ = two_users
    token = _open_website_session(a)
    handle = auth_sessions.website_session_handle(token)

    assert handle != token
    assert len(handle) == 64
    assert auth_sessions.restore_website_session_handle(handle) == a


@pytest.mark.parametrize("bad", [None, "", "A" * 64, "g" * 64, "0" * 63, 123])
def test_a_malformed_website_session_handle_is_refused(bad):
    assert auth_sessions.restore_website_session_handle(bad) is None


def test_a_streamlit_token_is_not_accepted(two_users):
    """Domain separation: the surfaces hash with different prefixes, so a token
    minted for one cannot hash to a row the other can find."""
    a, _ = two_users
    streamlit_token = auth_sessions.open_streamlit_session(a)
    assert auth_sessions.restore_website_session(streamlit_token) is None


def test_a_revoked_session_is_refused(two_users):
    a, _ = two_users
    token = _open_website_session(a)
    auth_sessions.revoke_all_for_user(a)
    assert auth_sessions.restore_website_session(token) is None


def test_a_session_past_its_absolute_expiry_is_refused(two_users):
    a, _ = two_users
    token = _open_website_session(a, expires_in=-1)
    assert auth_sessions.restore_website_session(token) is None


def test_an_idle_session_is_refused(two_users):
    a, _ = two_users
    stale = dt.datetime.now(dt.timezone.utc) - dt.timedelta(seconds=9 * 3600)
    token = _open_website_session(a, idle_at=stale)
    assert auth_sessions.restore_website_session(token) is None


def test_a_deactivated_account_is_refused(two_users):
    """The session row alone is not enough: a disabled account must not be able
    to act through a credential minted while it was still active."""
    a, _ = two_users
    token = _open_website_session(a)
    db = SessionLocal()
    try:
        db.execute(text("UPDATE users SET is_active = 0 WHERE id = :u"), {"u": a})
        db.commit()
    finally:
        db.close()
    assert auth_sessions.restore_website_session(token) is None


@pytest.mark.parametrize("bad", [None, "", 123, b"bytes", "not-a-real-token"])
def test_garbage_is_refused_without_raising(bad):
    assert auth_sessions.restore_website_session(bad) is None


def test_activity_slides_idle_but_never_extends_absolute_expiry(two_users):
    a, _ = two_users
    token = _open_website_session(a)
    db = SessionLocal()
    try:
        before = db.execute(
            text("SELECT expires_at FROM auth_sessions WHERE surface = 'website'")
        ).scalar()
    finally:
        db.close()

    auth_sessions.restore_website_session(token)

    db = SessionLocal()
    try:
        after = db.execute(
            text("SELECT expires_at FROM auth_sessions WHERE surface = 'website'")
        ).scalar()
    finally:
        db.close()
    assert before == after
