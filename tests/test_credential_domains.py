"""Cross-surface credential separation.

On 2026-08-13 a probe showed that a session created by the Python (Streamlit)
issuer was accepted by the TypeScript website validator, because both hashed
with a plain sha256 into one table with no surface marker.

That mattered because the credentials have deliberately different exposure: the
website one is an HttpOnly cookie, the Streamlit one rides in a URL and is a
documented leaky bearer. Interchangeability bridged the weakest credential to
the strongest.

Two redundant controls close it, and these tests hold both.
"""

from __future__ import annotations

import hashlib

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from src.tradelens.db.models import Base, User
from src.tradelens.services import auth_sessions


@pytest.fixture()
def db(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'domains.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    monkeypatch.setattr(auth_sessions, "SessionLocal", Session)
    s = Session()
    try:
        s.add(User(id=1, username="probe", password_hash="h", is_active=1))
        s.commit()
    finally:
        s.close()
    return Session


def _website_hash(token: str) -> str:
    """What the TypeScript website side stores, reproduced here."""
    return hashlib.sha256(
        (auth_sessions.WEBSITE_DOMAIN + token).encode("utf-8")
    ).hexdigest()


def test_the_two_domains_are_versioned_and_distinct():
    assert auth_sessions.WEBSITE_DOMAIN == "tl.website.v1|"
    assert auth_sessions.STREAMLIT_DOMAIN == "tl.streamlit.v1|"
    assert auth_sessions.WEBSITE_DOMAIN != auth_sessions.STREAMLIT_DOMAIN


def test_one_token_hashes_differently_per_domain():
    token = "the-same-raw-token"
    website = _website_hash(token)
    streamlit = auth_sessions._hash(token, auth_sessions.STREAMLIT_DOMAIN)
    assert website != streamlit
    # And neither equals the old undomained form.
    plain = hashlib.sha256(token.encode()).hexdigest()
    assert website != plain
    assert streamlit != plain


def test_a_streamlit_session_carries_the_streamlit_surface(db):
    auth_sessions.open_streamlit_session(1)
    s = db()
    try:
        surface = s.execute(text("SELECT surface FROM auth_sessions")).scalar()
    finally:
        s.close()
    assert surface == "streamlit"


def test_a_website_row_is_invisible_to_the_streamlit_validator(db):
    """The original exploit, in the direction Python can test.

    A row written the way the website writes one — website-domain hash, website
    surface — must not resolve through the Streamlit validator, even when the
    exact raw token is supplied.
    """
    token = "a-website-raw-token-copied-exactly"
    s = db()
    try:
        s.execute(
            text(
                "INSERT INTO auth_sessions "
                "(token_hash, user_id, created_at, expires_at, last_seen_at, surface) "
                "VALUES (:h, 1, :c, :e, :c, 'website')"
            ),
            {
                "h": _website_hash(token),
                "c": "2026-08-13 10:00:00",
                "e": "2099-08-13 10:00:00",
            },
        )
        s.commit()
    finally:
        s.close()

    assert auth_sessions.restore_streamlit_session(token) is None


def test_the_surface_filter_alone_would_not_be_enough(db):
    """Why the hash prefix carries the weight.

    Even a row planted with the *Streamlit* hash but the wrong surface is
    refused — the two controls are independent, and either one rejects.
    """
    token = "planted-token"
    s = db()
    try:
        s.execute(
            text(
                "INSERT INTO auth_sessions "
                "(token_hash, user_id, created_at, expires_at, last_seen_at, surface) "
                "VALUES (:h, 1, :c, :e, :c, 'website')"
            ),
            {
                "h": auth_sessions._hash(token, auth_sessions.STREAMLIT_DOMAIN),
                "c": "2026-08-13 10:00:00",
                "e": "2099-08-13 10:00:00",
            },
        )
        s.commit()
    finally:
        s.close()
    assert auth_sessions.restore_streamlit_session(token) is None


def test_no_undomained_fallback_exists():
    """A lookup that tried both forms would restore the ambiguity.

    auth_sessions was empty when the change landed, so a clean cut cost nothing
    and no legacy path is kept.
    """
    import inspect

    source = inspect.getsource(auth_sessions)
    # Every hash call must pass a domain; a bare _hash(token) would not.
    assert "_hash(token)" not in source
    assert "_hash(token, " in source


def test_revoke_all_crosses_surfaces(db):
    """Password reset must end the Streamlit session too, not only the website one."""
    streamlit_token = auth_sessions.open_streamlit_session(1)
    s = db()
    try:
        s.execute(
            text(
                "INSERT INTO auth_sessions "
                "(token_hash, user_id, created_at, expires_at, last_seen_at, surface) "
                "VALUES (:h, 1, :c, :e, :c, 'website')"
            ),
            {
                "h": _website_hash("w"),
                "c": "2026-08-13 10:00:00",
                "e": "2099-08-13 10:00:00",
            },
        )
        s.commit()
    finally:
        s.close()

    assert auth_sessions.revoke_all_for_user(1) == 2
    assert auth_sessions.restore_streamlit_session(streamlit_token) is None
