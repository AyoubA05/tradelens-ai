"""
User accounts service (Session B — multi-user auth).

Pure DB + bcrypt; no Streamlit. Login orchestration (DB-vs-secrets fallback)
and the invite-code check live in the UI layer (ui/components/auth.py); this
module only owns the users table and password hashing/verification.
"""

from __future__ import annotations

import re
import secrets
from datetime import datetime, timezone
from typing import Optional

import bcrypt

from src.tradelens.db.models import User
from src.tradelens.db.session import SessionLocal

_USERNAME_RE = re.compile(r"^[a-zA-Z0-9_]{3,20}$")
# Deliberately permissive: the only authority on whether an address works is
# whether mail to it arrives. This rejects the obviously-not-an-address cases
# so a typo is caught at entry, and nothing more.
_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s.]+(\.[^@\s.]+)+$")
MIN_PASSWORD_LEN = 8


def is_valid_username(username: str) -> bool:
    """3–20 chars, alphanumeric + underscore only."""
    return bool(_USERNAME_RE.match(username or ""))


def is_valid_email(email: str) -> bool:
    """True for a plausibly-deliverable address."""
    return bool(_EMAIL_RE.match((email or "").strip()))


def normalise_email(email):
    """Lowercase and trim, or None when blank.

    Stored lowercase so uniqueness and lookup mean the same thing however
    the address was typed.
    """
    cleaned = (email or "").strip().lower()
    return cleaned or None


def get_user_by_email(email):
    """Return the account owning this address, or None.

    A blank address returns None rather than matching the accounts that
    have no email at all.
    """
    normalised = normalise_email(email)
    if normalised is None:
        return None
    db = SessionLocal()
    try:
        return db.query(User).filter(User.email == normalised).first()
    finally:
        db.close()


def set_email(user_id: int, email) -> Optional[str]:
    """Set or clear an account's email. Returns the stored value.

    Raises ValueError for a malformed address, or one already belonging to
    a different account.
    """
    normalised = normalise_email(email)
    if normalised is not None and not is_valid_email(normalised):
        raise ValueError("Enter a valid email address, or leave it blank.")

    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if user is None:
            raise ValueError("No such account.")

        if normalised is not None:
            clash = (
                db.query(User)
                .filter(User.email == normalised, User.id != user_id)
                .first()
            )
            if clash is not None:
                raise ValueError("That email is already used by another account.")

        # Changing the address invalidates any verification of the old one, and
        # a newly typed address has never been verified at all.
        #
        # This closes a hole opened by the legacy backfill. Accounts predating
        # verification carry email_verification_required = False so they keep
        # signing in by username. Without the two lines below, the first email
        # such a user ever typed would inherit that exemption and be treated as
        # trusted — so an address nobody controls could receive a password
        # reset. Requirement is re-armed here on any change, which is exactly
        # the moment the exemption stops being about legacy access.
        if user.email != normalised:
            user.email_verified_at = None
            user.email_verification_required = True

        user.email = normalised
        db.commit()
        return normalised
    finally:
        db.close()


def users_exist() -> bool:
    """True once at least one DB user has been created."""
    db = SessionLocal()
    try:
        return db.query(User).count() > 0
    finally:
        db.close()


def get_user(username: str) -> Optional[User]:
    db = SessionLocal()
    try:
        return db.query(User).filter(User.username == username).first()
    finally:
        db.close()


def get_user_by_id(user_id) -> Optional[User]:
    """Return an account by id, or None. Tolerates the legacy None owner."""
    if user_id is None:
        return None
    db = SessionLocal()
    try:
        return db.query(User).filter(User.id == user_id).first()
    finally:
        db.close()


def username_taken(username: str) -> bool:
    return get_user(username) is not None


def hash_password(password: str) -> str:
    """bcrypt hash, stored as a UTF-8 string."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def create_user(username: str, password: str) -> User:
    """Insert a new user with a bcrypt-hashed password. Returns the saved User.

    Caller is responsible for validation (username format, password length,
    uniqueness, invite code) — this performs the insert only.
    """
    now = datetime.now(timezone.utc).isoformat()
    db = SessionLocal()
    try:
        user = User(
            username=username,
            password_hash=hash_password(password),
            is_active=1,
            created_at=now,
        )
        db.add(user)
        db.commit()
        db.refresh(user)
        return user
    finally:
        db.close()


def authenticate(username: str, password: str) -> Optional[User]:
    """Return the active User when the bcrypt password matches, else None."""
    user = get_user(username)
    if user is None or not user.is_active:
        return None
    try:
        if bcrypt.checkpw(password.encode("utf-8"), user.password_hash.encode("utf-8")):
            return user
    except (ValueError, TypeError):
        return None
    return None


# ---------------------------------------------------------------------------
# Site-hosted signup and login (Phase 2)
# ---------------------------------------------------------------------------

# Opaque internal usernames for accounts created through the site, which never
# asks the user to choose one.
#
# Deliberately NOT derived from the email local part. The username is not a
# private value — it is the legacy login identifier and shows up in support and
# admin contexts — so deriving it from the address would leak the local part
# wherever the username appears, and would make two people sharing a local part
# at different domains collide for no reason.
#
# "u_" + 16 hex characters is 18, inside the existing 3-20 constraint that every
# legacy username already satisfies.
_INTERNAL_USERNAME_PREFIX = "u_"
_INTERNAL_USERNAME_ENTROPY_BYTES = 8  # 64 bits -> 16 hex chars


def generate_internal_username() -> str:
    """An opaque username for an account whose owner never picked one."""
    return _INTERNAL_USERNAME_PREFIX + secrets.token_hex(
        _INTERNAL_USERNAME_ENTROPY_BYTES
    )


def resolve_login_identifier(identifier) -> Optional[User]:
    """Resolve a login identifier to an account. Explicit precedence, no fallthrough.

    An identifier containing "@" is resolved **by email only**. It does not fall
    back to a username lookup on failure: the fallthrough would be the ambiguous
    case, and it cannot arise anyway because usernames are constrained to
    ``[a-zA-Z0-9_]`` and can never contain "@".

    Anything else is resolved by username, **exact and case-sensitive**. The two
    legacy accounts ``ayoub`` and ``Ayoub`` are genuinely distinct rows, and
    case-folding here would silently merge two people's journals.
    """
    value = (identifier or "").strip()
    if not value:
        return None
    if "@" in value:
        return get_user_by_email(value)
    return get_user(value)


def email_login_allowed(user: Optional[User]) -> bool:
    """Whether this account may authenticate with its email address.

    False until the address is verified. An unverified address is one nobody has
    proven they control, so treating it as a login identifier would make it a
    second door into the account for whoever typed it.
    """
    if user is None or user.email is None:
        return False
    return user.email_verified_at is not None


def password_reset_allowed(user: Optional[User]) -> bool:
    """Whether a reset code may be sent to this account's address.

    Same rule, and the more important of the two: delivering a reset code to an
    unproven address hands over the account.
    """
    return email_login_allowed(user)


def login_blocked_pending_verification(user: Optional[User]) -> bool:
    """Whether this account is held back until it verifies its email.

    Only accounts created by the new signup flow are: they carry
    ``email_verification_required = True``. Legacy accounts were exempted by the
    s9 backfill, so they keep signing in by username exactly as before — without
    us having fabricated an ``email_verified_at`` they never earned.
    """
    if user is None:
        return False
    return bool(user.email_verification_required) and user.email_verified_at is None


def get_onboarding_state(user_id) -> dict:
    """Onboarding flags for a user, or an all-false default for the legacy None id."""
    user = get_user_by_id(user_id)
    if user is None:
        return {
            "onboarding_completed": False,
            "strategy_profile_completed": False,
            "email_verified": False,
        }
    return {
        "onboarding_completed": bool(user.onboarding_completed),
        "strategy_profile_completed": bool(user.strategy_profile_completed),
        "email_verified": user.email_verified_at is not None,
    }


def mark_strategy_profile_completed(user_id: int) -> None:
    """Record that the first-run Strategy Profile step is done.

    Set by both exits of that screen — saving a profile and choosing "I don't
    have a defined strategy yet". The second writes no Strategy row, which is
    exactly why this is a stored flag and not derived from whether one exists.
    """
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if user is None:
            raise ValueError("No such account.")
        user.strategy_profile_completed = True
        db.commit()
    finally:
        db.close()


def mark_email_verified(user_id: int) -> None:
    """Record successful verification of the account's current address."""
    db = SessionLocal()
    try:
        user = db.query(User).filter(User.id == user_id).first()
        if user is None:
            raise ValueError("No such account.")
        user.email_verified_at = datetime.now(timezone.utc)
        user.onboarding_completed = True
        db.commit()
    finally:
        db.close()
