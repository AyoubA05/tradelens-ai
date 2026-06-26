"""
Multi-user signup + login tests (Session B, Section 0).

The pure orchestration (auth.process_signup / auth.authenticate_login) and the
users service are exercised against an in-memory DB. The Streamlit forms are not
imported here (they run Streamlit at import time).
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import src.tradelens.services.users as users
import src.tradelens.ui.components.auth as auth
from src.tradelens.db.models import Base, User


@pytest.fixture
def db_session(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    InMemorySession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(users, "SessionLocal", InMemorySession)
    yield InMemorySession
    Base.metadata.drop_all(engine)


def test_signup_valid_invite_code(db_session, monkeypatch):
    monkeypatch.setenv("TRADELENS_INVITE_CODE", "SECRET")
    err = auth.process_signup("alice", "password123", "password123", "SECRET")
    assert err is None
    assert users.username_taken("alice")


def test_signup_invalid_invite_code(db_session, monkeypatch):
    monkeypatch.setenv("TRADELENS_INVITE_CODE", "SECRET")
    err = auth.process_signup("bob", "password123", "password123", "WRONG")
    assert err == "Invalid invite code."
    assert not users.username_taken("bob")


def test_signup_duplicate_username(db_session, monkeypatch):
    monkeypatch.setenv("TRADELENS_INVITE_CODE", "SECRET")
    auth.process_signup("carol", "password123", "password123", "SECRET")
    err = auth.process_signup("carol", "password123", "password123", "SECRET")
    assert err == "Username already taken."


def test_signup_short_password_rejected(db_session, monkeypatch):
    monkeypatch.setenv("TRADELENS_INVITE_CODE", "SECRET")
    err = auth.process_signup("dan", "short", "short", "SECRET")
    assert err and "8 characters" in err
    assert not users.username_taken("dan")


def test_login_db_user(db_session):
    users.create_user("dave", "password123")
    ok, uname, uid = auth.authenticate_login("dave", "password123")
    assert ok and uname == "dave" and uid is not None
    bad_ok, _, _ = auth.authenticate_login("dave", "wrongpass")
    assert bad_ok is False


def test_login_secrets_fallback(db_session, monkeypatch):
    # users table is empty → secrets credentials are accepted, user_id is None.
    monkeypatch.setenv("TRADELENS_USERNAME", "demo")
    monkeypatch.setenv("TRADELENS_PASSWORD", "tradelens2025")
    ok, uname, uid = auth.authenticate_login("demo", "tradelens2025")
    assert ok and uname == "demo" and uid is None


def test_db_users_take_precedence_over_secrets(db_session, monkeypatch):
    # Once a DB user exists, the secrets fallback must NOT authenticate.
    monkeypatch.setenv("TRADELENS_USERNAME", "demo")
    monkeypatch.setenv("TRADELENS_PASSWORD", "tradelens2025")
    users.create_user("realuser", "password123")
    ok, _, _ = auth.authenticate_login("demo", "tradelens2025")
    assert ok is False


def test_password_not_stored_plain(db_session):
    users.create_user("erin", "supersecret123")
    user = users.get_user("erin")
    assert isinstance(user, User)
    assert "supersecret123" not in user.password_hash
    assert user.password_hash.startswith("$2")  # bcrypt hash prefix
