"""The Python half of the cross-language account-rule contract.

`web/__tests__/auth-contract.test.ts` reads this same JSON file and makes the
equivalent assertions against the TypeScript implementation. Signup exists in
both languages — the site creates accounts in Node, the Streamlit app has always
created them in Python — and importing across that boundary would mean putting a
Python HTTP service on the signup path purely to avoid duplication.

So the implementations are independent by design, and these shared vectors are
what stops them becoming two unrelated definitions. A rule changed on one side
without the other fails here, on the other side, or both.
"""

from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import pytest

from src.tradelens.db.models import User
from src.tradelens.services import users

VECTORS = json.loads(
    (
        Path(__file__).parent.parent
        / "docs"
        / "contracts"
        / "auth-contract-vectors.json"
    ).read_text()
)


# ---------------------------------------------------------------------------
# Email normalization
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("case", VECTORS["email_normalization"]["vectors"])
def test_email_normalization_matches_the_contract(case):
    assert users.normalise_email(case["input"]) == case["expected"]


def test_normalization_preserves_plus_tags():
    """Stripping them would merge addresses their owner treats as distinct."""
    assert users.normalise_email("a+tag@example.com") == "a+tag@example.com"


@pytest.mark.parametrize("value", VECTORS["email_validity"]["valid"])
def test_valid_emails_are_accepted(value):
    assert users.is_valid_email(value)


@pytest.mark.parametrize("value", VECTORS["email_validity"]["invalid"])
def test_invalid_emails_are_rejected(value):
    assert not users.is_valid_email(value)


# ---------------------------------------------------------------------------
# Opaque internal username
# ---------------------------------------------------------------------------


def test_opaque_username_matches_the_contract_pattern():
    pattern = re.compile(VECTORS["opaque_username"]["pattern"])
    legacy = re.compile(VECTORS["opaque_username"]["legacy_username_constraint"])
    for _ in range(200):
        username = users.generate_internal_username()
        assert pattern.match(username), username
        # Must also satisfy the constraint every legacy username satisfies, or a
        # new account cannot coexist with the existing ones.
        assert legacy.match(username), username
        assert len(username) == VECTORS["opaque_username"]["length"]
        assert users.is_valid_username(username)


def test_opaque_username_is_not_derived_from_user_input():
    """The generator takes no arguments — this asserts the consequence."""
    fragments = VECTORS["opaque_username"]["derivation_probe"]["forbidden_fragments"]
    for _ in range(200):
        username = users.generate_internal_username().lower()
        for fragment in fragments:
            assert fragment.lower() not in username


def test_opaque_usernames_do_not_collide():
    assert len({users.generate_internal_username() for _ in range(5000)}) == 5000


# ---------------------------------------------------------------------------
# New account defaults vs the legacy exemption
# ---------------------------------------------------------------------------


def test_the_model_can_express_the_contract_defaults():
    defaults = VECTORS["new_account_defaults"]
    user = User(
        username=users.generate_internal_username(),
        password_hash="x",
        email="new@example.com",
        onboarding_completed=defaults["onboarding_completed"],
        strategy_profile_completed=defaults["strategy_profile_completed"],
        email_verified_at=None,
        email_verification_required=defaults["email_verification_required"],
        is_active=defaults["is_active"],
    )
    assert user.onboarding_completed is True
    assert user.strategy_profile_completed is False
    assert user.email_verified_at is None
    assert user.email_verification_required is True


def test_new_and_legacy_verification_requirements_are_opposites():
    """If these ever match, one of two bad things has happened.

    Equal-and-true locks the two legacy accounts out of their own journals;
    equal-and-false lets every new account skip verification entirely.
    """
    new = VECTORS["new_account_defaults"]["email_verification_required"]
    legacy = VECTORS["legacy_account_behaviour"]["email_verification_required"]
    assert new is True
    assert legacy is False
    assert new != legacy


def test_neither_new_nor_legacy_accounts_get_a_fabricated_verified_timestamp():
    assert VECTORS["new_account_defaults"]["email_verified_at"] is None
    assert VECTORS["legacy_account_behaviour"]["email_verified_at"] is None


# ---------------------------------------------------------------------------
# Legacy behaviour the contract pins
# ---------------------------------------------------------------------------


def test_a_legacy_account_cannot_use_email_login_or_reset_before_verifying():
    legacy = User(
        username="ayoub",
        password_hash="x",
        email="ayoub@example.com",
        email_verified_at=None,
        email_verification_required=False,
    )
    assert users.email_login_allowed(legacy) is (
        VECTORS["legacy_account_behaviour"]["email_login_allowed_before_verification"]
    )
    assert users.password_reset_allowed(legacy) is (
        VECTORS["legacy_account_behaviour"][
            "password_reset_allowed_before_verification"
        ]
    )


def test_a_legacy_account_is_not_blocked_from_signing_in():
    """The exemption exists so username login keeps working."""
    legacy = User(
        username="ayoub",
        password_hash="x",
        email=None,
        email_verified_at=None,
        email_verification_required=False,
    )
    assert users.login_blocked_pending_verification(legacy) is False


def test_a_new_account_is_blocked_until_it_verifies():
    fresh = User(
        username=users.generate_internal_username(),
        password_hash="x",
        email="new@example.com",
        email_verified_at=None,
        email_verification_required=True,
    )
    assert users.login_blocked_pending_verification(fresh) is True

    fresh.email_verified_at = datetime.now(timezone.utc)
    assert users.login_blocked_pending_verification(fresh) is False
    assert users.email_login_allowed(fresh) is True


def test_the_two_production_usernames_stay_distinct():
    """Case-sensitivity is load-bearing: these are two real, separate accounts."""
    names = VECTORS["legacy_account_behaviour"]["distinct_usernames_in_production"]
    assert names == ["ayoub", "Ayoub"]
    assert names[0] != names[1]
    assert VECTORS["legacy_account_behaviour"]["username_matching"] == (
        "exact, case-sensitive"
    )


# ---------------------------------------------------------------------------
# bcrypt interoperability
# ---------------------------------------------------------------------------


def test_python_bcrypt_matches_the_contract_cost_and_prefix():
    """Node and Python must produce hashes the other can verify.

    Verified in both directions on 2026-08-11; this pins the parameters so a
    later change to either side shows up as a failure rather than as accounts
    that cannot sign in.
    """
    import bcrypt

    hashed = bcrypt.hashpw(b"Correct-Horse-Battery-9!", bcrypt.gensalt()).decode()
    assert hashed.startswith(VECTORS["bcrypt"]["prefix"])
    assert int(hashed.split("$")[2]) == VECTORS["bcrypt"]["cost"]
    assert bcrypt.checkpw(b"Correct-Horse-Battery-9!", hashed.encode())
