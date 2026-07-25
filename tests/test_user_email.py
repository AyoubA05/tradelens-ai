"""The optional email address, and what it is allowed to promise.

Email is the only route back into an account, so the rules that matter are:
it is genuinely optional, it identifies exactly one account when present,
and lookups are case-insensitive (people do not retype their address the
way they first typed it).
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import src.tradelens.services.users as users_service
from src.tradelens.db.models import Base, User


@pytest.fixture
def in_memory_db(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    InMemorySession = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(users_service, "SessionLocal", InMemorySession)
    yield InMemorySession
    Base.metadata.drop_all(engine)


# --- validation ------------------------------------------------------------


@pytest.mark.parametrize(
    "address",
    ["a@b.co", "trader.one@example.com", "x+tag@sub.domain.org"],
)
def test_plausible_addresses_are_accepted(address):
    assert users_service.is_valid_email(address)


@pytest.mark.parametrize(
    "address",
    ["", "   ", "no-at-sign", "@nodomain.com", "user@", "user@nodot", "a b@c.com"],
)
def test_implausible_addresses_are_rejected(address):
    assert not users_service.is_valid_email(address)


def test_normalisation_lowercases_and_trims():
    assert (
        users_service.normalise_email("  Trader@Example.COM ") == "trader@example.com"
    )


def test_normalising_a_blank_address_gives_none():
    assert users_service.normalise_email("") is None
    assert users_service.normalise_email(None) is None


# --- storage ---------------------------------------------------------------


def test_account_without_an_email_is_valid(in_memory_db):
    user = users_service.create_user("trader", "DemoPass!2026x")
    assert user.email is None


def test_email_can_be_set_and_is_stored_normalised(in_memory_db):
    user = users_service.create_user("trader", "DemoPass!2026x")
    users_service.set_email(user.id, "  Trader@Example.COM ")
    assert users_service.get_user("trader").email == "trader@example.com"


def test_email_can_be_cleared(in_memory_db):
    user = users_service.create_user("trader", "DemoPass!2026x")
    users_service.set_email(user.id, "trader@example.com")
    users_service.set_email(user.id, "")
    assert users_service.get_user("trader").email is None


def test_invalid_email_is_rejected_rather_than_stored(in_memory_db):
    user = users_service.create_user("trader", "DemoPass!2026x")
    with pytest.raises(ValueError, match="valid email"):
        users_service.set_email(user.id, "not-an-address")


def test_two_accounts_cannot_share_an_address(in_memory_db):
    first = users_service.create_user("trader", "DemoPass!2026x")
    second = users_service.create_user("other", "DemoPass!2026x")
    users_service.set_email(first.id, "shared@example.com")
    with pytest.raises(ValueError, match="already"):
        users_service.set_email(second.id, "SHARED@example.com")


def test_setting_the_same_address_again_is_not_a_conflict(in_memory_db):
    user = users_service.create_user("trader", "DemoPass!2026x")
    users_service.set_email(user.id, "trader@example.com")
    users_service.set_email(user.id, "Trader@Example.com")  # must not raise
    assert users_service.get_user("trader").email == "trader@example.com"


def test_many_accounts_may_have_no_email(in_memory_db):
    """Optional has to mean optional for more than one account."""
    users_service.create_user("a", "DemoPass!2026x")
    users_service.create_user("b", "DemoPass!2026x")
    users_service.create_user("c", "DemoPass!2026x")
    db = in_memory_db()
    try:
        assert db.query(User).filter(User.email.is_(None)).count() == 3
    finally:
        db.close()


# --- lookup ----------------------------------------------------------------


def test_lookup_by_email_is_case_insensitive(in_memory_db):
    user = users_service.create_user("trader", "DemoPass!2026x")
    users_service.set_email(user.id, "trader@example.com")
    found = users_service.get_user_by_email("  TRADER@Example.com  ")
    assert found is not None
    assert found.username == "trader"


def test_lookup_of_an_unknown_address_returns_none(in_memory_db):
    assert users_service.get_user_by_email("nobody@example.com") is None


def test_lookup_of_a_blank_address_returns_none(in_memory_db):
    """A blank address must never match the email-less accounts."""
    users_service.create_user("trader", "DemoPass!2026x")
    assert users_service.get_user_by_email("") is None
    assert users_service.get_user_by_email(None) is None
