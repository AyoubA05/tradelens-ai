"""
User accounts service (Session B — multi-user auth).

Pure DB + bcrypt; no Streamlit. Login orchestration (DB-vs-secrets fallback)
and the invite-code check live in the UI layer (ui/components/auth.py); this
module only owns the users table and password hashing/verification.
"""

from __future__ import annotations

import re
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
