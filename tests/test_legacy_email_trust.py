"""Legacy accounts must keep access without their emails becoming trusted.

Production on 2026-08-10 held 2 users, both with no email at all. The migration
exempts them from verification so username login keeps working. That exemption
is about *retaining access*, and it must not silently become a statement that
any address they later type is confirmed.

The failure this guards against: a legacy user adds an address with a typo, or
an attacker with a session adds their own, and — because the account was
exempt — password reset immediately treats it as a trusted route into the
account.
"""

from __future__ import annotations

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.tradelens.db.models import Base, User
from src.tradelens.services import users


@pytest.fixture()
def db(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    monkeypatch.setattr(users, "SessionLocal", Session)
    return Session


def _legacy_user(Session) -> int:
    """An account shaped like the two in production: no email, exempt."""
    session = Session()
    try:
        user = User(
            username="legacy",
            password_hash="h",
            is_active=1,
            email=None,
            email_verified_at=None,
            email_verification_required=False,
            onboarding_completed=True,
            strategy_profile_completed=False,
        )
        session.add(user)
        session.commit()
        return user.id
    finally:
        session.close()


def test_adding_an_email_to_a_legacy_account_requires_verification(db):
    """The exemption must not transfer to a freshly typed address."""
    user_id = _legacy_user(db)

    users.set_email(user_id, "ayoub@example.com")

    session = db()
    try:
        user = session.get(User, user_id)
        assert user.email == "ayoub@example.com"
        assert user.email_verified_at is None, "a new address starts unverified"
        assert user.email_verification_required, (
            "the legacy exemption must be re-armed the moment an address is "
            "added, or an unverified address inherits trust"
        )
    finally:
        session.close()


def test_changing_a_verified_email_revokes_the_verification(db):
    """Verification attaches to an address, not to an account."""
    from datetime import datetime, timezone

    user_id = _legacy_user(db)
    session = db()
    try:
        user = session.get(User, user_id)
        user.email = "old@example.com"
        user.email_verified_at = datetime.now(timezone.utc)
        user.email_verification_required = True
        session.commit()
    finally:
        session.close()

    users.set_email(user_id, "new@example.com")

    session = db()
    try:
        user = session.get(User, user_id)
        assert user.email == "new@example.com"
        assert (
            user.email_verified_at is None
        ), "the new address inherited the old address's verification"
    finally:
        session.close()


def test_rewriting_the_same_email_does_not_revoke_verification(db):
    """An idempotent save must not silently sign the user out of their address."""
    from datetime import datetime, timezone

    user_id = _legacy_user(db)
    verified_at = datetime.now(timezone.utc)
    session = db()
    try:
        user = session.get(User, user_id)
        user.email = "same@example.com"
        user.email_verified_at = verified_at
        session.commit()
    finally:
        session.close()

    users.set_email(user_id, "  SAME@example.com  ")  # same address, messy input

    session = db()
    try:
        user = session.get(User, user_id)
        assert (
            user.email_verified_at is not None
        ), "normalisation means this is the same address; verification stands"
    finally:
        session.close()


def test_clearing_an_email_clears_its_verification(db):
    from datetime import datetime, timezone

    user_id = _legacy_user(db)
    session = db()
    try:
        user = session.get(User, user_id)
        user.email = "gone@example.com"
        user.email_verified_at = datetime.now(timezone.utc)
        session.commit()
    finally:
        session.close()

    users.set_email(user_id, None)

    session = db()
    try:
        user = session.get(User, user_id)
        assert user.email is None
        assert user.email_verified_at is None
    finally:
        session.close()
