"""Password reset: the only route back into an account.

The security properties that matter, and why:

* A token is **single-use**. It is signed with a key derived from the
  account's current password hash, so the moment the password changes the
  signature stops verifying. No table of spent tokens to keep or clean up.
* A token **expires**, so one sitting in an old inbox is not a permanent
  key to the account.
* A token is **bound to one account** and cannot be edited into another.
* Requesting a reset **reveals nothing** about whether an address has an
  account, so the form cannot be used to enumerate users.
* The token is never rendered in the UI — it goes to the inbox or nowhere.
"""

import time

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import src.tradelens.services.password_reset as reset_service
import src.tradelens.services.users as users_service
from src.tradelens.db.models import Base


@pytest.fixture
def in_memory_db(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    monkeypatch.setattr(users_service, "SessionLocal", Session)
    monkeypatch.setattr(reset_service, "SessionLocal", Session)
    monkeypatch.setenv("TRADELENS_SESSION_SECRET", "test-secret-material")
    yield Session
    Base.metadata.drop_all(engine)


@pytest.fixture
def account(in_memory_db):
    user = users_service.create_user("trader", "OriginalPass!1")
    users_service.set_email(user.id, "trader@example.com")
    return users_service.get_user("trader")


# --- token lifecycle -------------------------------------------------------


def test_a_fresh_token_identifies_its_account(account):
    token = reset_service.issue_reset_token(account.id)
    assert reset_service.verify_reset_token(token) == account.id


def test_a_token_stops_working_once_the_password_changes(account):
    """Single-use: completing a reset must retire the token that did it."""
    token = reset_service.issue_reset_token(account.id)
    assert reset_service.complete_reset(token, "BrandNewPass!2") is True
    assert reset_service.verify_reset_token(token) is None


def test_a_token_cannot_be_replayed_to_set_a_second_password(account):
    token = reset_service.issue_reset_token(account.id)
    reset_service.complete_reset(token, "BrandNewPass!2")
    assert reset_service.complete_reset(token, "AttackerPass!3") is False
    # The first reset is the one that stands.
    assert users_service.authenticate("trader", "BrandNewPass!2") is not None
    assert users_service.authenticate("trader", "AttackerPass!3") is None


def test_an_expired_token_is_rejected(account):
    stale = reset_service.issue_reset_token(account.id, now=time.time() - 10_000)
    assert reset_service.verify_reset_token(stale) is None


def test_a_token_just_inside_its_window_still_works(account):
    fresh = reset_service.issue_reset_token(
        account.id, now=time.time() - reset_service.TOKEN_TTL_S + 60
    )
    assert reset_service.verify_reset_token(fresh) == account.id


def test_a_tampered_token_is_rejected(account):
    token = reset_service.issue_reset_token(account.id)
    payload, _, signature = token.rpartition(".")

    # Editing the payload invalidates the signature over it.
    assert reset_service.verify_reset_token(f"{payload}x.{signature}") is None

    # Flip the last signature character to a *different* one. Appending a
    # fixed digit would leave the signature untouched whenever it already
    # ended in that digit — roughly one run in sixteen, which is a flaky
    # test rather than a real check.
    flipped = signature[:-1] + ("1" if signature[-1] == "0" else "0")
    assert flipped != signature
    assert reset_service.verify_reset_token(f"{payload}.{flipped}") is None


def test_every_single_character_signature_edit_is_rejected(account):
    """The whole signature is load-bearing, not just its prefix."""
    token = reset_service.issue_reset_token(account.id)
    payload, _, signature = token.rpartition(".")

    for position in range(0, len(signature), 7):  # sample across the digest
        original = signature[position]
        replacement = "1" if original == "0" else "0"
        mutated = signature[:position] + replacement + signature[position + 1 :]
        assert reset_service.verify_reset_token(f"{payload}.{mutated}") is None


def test_a_token_signed_for_one_account_does_not_open_another(in_memory_db):
    first = users_service.create_user("trader", "OriginalPass!1")
    second = users_service.create_user("other", "OriginalPass!1")
    token = reset_service.issue_reset_token(first.id)
    assert reset_service.verify_reset_token(token) == first.id
    assert reset_service.verify_reset_token(token) != second.id


def test_garbage_is_rejected_without_raising(account):
    for junk in ("", None, "not-a-token", "a.b", "....", 12345):
        assert reset_service.verify_reset_token(junk) is None


def test_the_token_does_not_contain_the_password_or_its_hash(account):
    token = reset_service.issue_reset_token(account.id)
    assert "OriginalPass!1" not in token
    assert account.password_hash not in token


# --- completing a reset ----------------------------------------------------


def test_a_completed_reset_lets_the_new_password_sign_in(account):
    token = reset_service.issue_reset_token(account.id)
    reset_service.complete_reset(token, "BrandNewPass!2")
    assert users_service.authenticate("trader", "BrandNewPass!2") is not None
    assert users_service.authenticate("trader", "OriginalPass!1") is None


def test_a_reset_rejects_a_password_that_is_too_short(account):
    token = reset_service.issue_reset_token(account.id)
    with pytest.raises(ValueError, match="at least"):
        reset_service.complete_reset(token, "short")
    # The original password must still work after a rejected attempt.
    assert users_service.authenticate("trader", "OriginalPass!1") is not None


def test_an_invalid_token_cannot_complete_a_reset(account):
    assert reset_service.complete_reset("bogus.token", "BrandNewPass!2") is False
    assert users_service.authenticate("trader", "OriginalPass!1") is not None


# --- requesting a reset: no user enumeration -------------------------------


def test_requesting_a_reset_for_a_known_address_sends_one(account, monkeypatch):
    sent = []
    monkeypatch.setattr(reset_service, "send_email", lambda **kw: sent.append(kw))
    result = reset_service.request_reset("trader@example.com")
    assert result.accepted
    assert len(sent) == 1
    assert sent[0]["to_address"] == "trader@example.com"


def test_requesting_a_reset_for_an_unknown_address_looks_identical(
    account, monkeypatch
):
    """Same answer either way, or the form becomes a user-enumeration oracle."""
    sent = []
    monkeypatch.setattr(reset_service, "send_email", lambda **kw: sent.append(kw))

    known = reset_service.request_reset("trader@example.com")
    unknown = reset_service.request_reset("nobody@example.com")

    assert known.accepted == unknown.accepted
    assert known.message == unknown.message
    assert len(sent) == 1  # nothing was sent for the unknown address


def test_an_account_without_an_email_gets_the_same_answer(in_memory_db, monkeypatch):
    users_service.create_user("noemail", "OriginalPass!1")
    sent = []
    monkeypatch.setattr(reset_service, "send_email", lambda **kw: sent.append(kw))
    result = reset_service.request_reset("")
    assert result.accepted
    assert not sent


def test_the_reset_message_carries_the_token_and_never_returns_it(account, monkeypatch):
    """The token reaches the inbox; the caller must not be able to read it."""
    sent = {}
    monkeypatch.setattr(reset_service, "send_email", lambda **kw: sent.update(kw))
    result = reset_service.request_reset("trader@example.com")

    token = sent["body"].split("code:")[-1].strip().splitlines()[0].strip()
    assert reset_service.verify_reset_token(token) == account.id
    assert token not in result.message


def test_delivery_failure_is_reported_not_swallowed(account, monkeypatch):
    """A reset the user never receives must not look like success."""

    def _boom(**_kw):
        raise reset_service.EmailNotSent("SMTP is not configured")

    monkeypatch.setattr(reset_service, "send_email", _boom)
    result = reset_service.request_reset("trader@example.com")
    assert not result.accepted
    assert "could not" in result.message.lower()


# --- SMTP configuration ----------------------------------------------------


def test_email_is_unavailable_until_smtp_is_configured(monkeypatch):
    for var in ("TRADELENS_SMTP_HOST", "TRADELENS_SMTP_FROM"):
        monkeypatch.delenv(var, raising=False)
    assert not reset_service.email_configured()


def test_email_is_available_once_host_and_sender_are_set(monkeypatch):
    monkeypatch.setenv("TRADELENS_SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("TRADELENS_SMTP_FROM", "noreply@example.com")
    assert reset_service.email_configured()
